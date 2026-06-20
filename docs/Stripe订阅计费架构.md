# Stripe 订阅计费架构

本文是 StratArk Stripe Billing 集成的当前事实源，覆盖后端、前端、配置、数据落库与失败边界。

## 一、集成原则

- 付费套餐切换只走 Stripe Checkout，前端不接触 Stripe 密钥、Price ID 或签名逻辑。
- 订阅生效以 Stripe Webhook 回写为准，`checkoutUrl` 返回不代表本地套餐已经升级。
- 未完整配置 Stripe 时，付费切换必须返回明确业务错误，不做本地付费回退。
- 套餐展示数据落库在 `plans` 表，Stripe Product / Price ID 也落库，不走 env。
- 发票以 Stripe `invoice.paid` / `invoice.payment_succeeded` 事件为准，优先保存 Stripe 托管 PDF 链接。

## 二、配置边界

后端只需要三项运行时配置：

```dotenv
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
FRONTEND_BASE_URL=
```

- `STRIPE_SECRET_KEY`：调用 Stripe API，用于 Product / Price 同步、Customer、Checkout、Portal、取消订阅。
- `STRIPE_WEBHOOK_SECRET`：验签 `/webhooks/stripe`，缺失时不得发起 Checkout。
- `FRONTEND_BASE_URL`：Checkout success / cancel 和 Customer Portal 返回地址；留空时取首个 `CORS_ORIGINS`。

代码里的状态拆分：

- `billing.stripe_api_enabled()`：仅表示可调用 Stripe API。
- `billing.stripe_webhook_enabled()`：仅表示可验签 Webhook。
- `billing.stripe_enabled()`：表示 Billing 完整可用，即 API 与 Webhook 密钥均已配置。

## 三、后端模块分层

- `libs/integrations/billing.py`：唯一 Stripe SDK 封装层；设置 API version、创建 Customer / Checkout / Portal、同步 Product / Price、验签 Webhook。
- `api/subscription/__init__.py`：路由层，只做参数映射、依赖注入和 Stripe Webhook HTTP 状态码映射。
- `view_models/subscription/__init__.py`：订阅业务编排，处理套餐目录、Checkout、Portal、取消、Webhook、发票。
- `models/subscription.py`：`plans`、`subscriptions`、`usage_counters`、`invoices`。
- `responses/subscription.py` 与 `forms/subscription.py`：前后端契约类型。

## 四、核心流程

### 4.1 后台同步套餐到 Stripe

1. 管理员编辑 `plans` 表中的套餐元数据。
2. 管理员调用 `POST /admin/plans/{code}/sync`。
3. 后端用 `STRIPE_SECRET_KEY` 创建或更新 Stripe Product。
4. 后端按月付 / 年付金额创建 Stripe recurring Price。
5. Price 金额未变化时复用旧 Price；金额变化时新建 Price 并归档旧 Price。
6. 回填 `stripe_product_id`、`stripe_price_monthly_id`、`stripe_price_yearly_id` 到 `plans` 表。

### 4.2 用户发起付费套餐切换

1. 前端调用 `POST /subscription/checkout`，传 `targetPlan` 与 `billingCycle`。
2. 后端确认 `STRIPE_SECRET_KEY` 与 `STRIPE_WEBHOOK_SECRET` 均已配置。
3. 后端读取目标套餐对应周期的 Stripe Price ID；缺失则要求管理员先同步。
4. 后端创建或复用 Stripe Customer，并回填 `users.stripe_customer_id`。
5. 后端创建 `mode=subscription` 的 Checkout Session，metadata 写入 `userId`、`plan`、`cycle`。
6. 前端跳转 `checkoutUrl`。
7. 用户完成支付后 Stripe 回调 `/webhooks/stripe`。
8. 本地订阅状态只在 Webhook 验签成功后更新。

### 4.3 Webhook 回写

支持事件：

- `checkout.session.completed`：按 metadata 找用户与套餐，按 Stripe subscription ID 幂等创建或更新本地 active 订阅。
- `customer.subscription.updated`：更新当前周期结束时间与订阅状态。
- `customer.subscription.deleted`：本地订阅置为 canceled，并把用户降回 free。
- `invoice.paid` / `invoice.payment_succeeded`：按发票号幂等写入 `invoices`，优先保存 `hosted_invoice_url` 或 `invoice_pdf`。

幂等边界：

- 订阅事件以 `stripe_subscription_id` 去重，重复 Checkout 完成事件不会重复新建 active 订阅。
- 发票事件以 `invoice_no` 去重，同一 Stripe 发票不会重复落库。

### 4.4 客户门户与取消

- 前端取消订阅时优先打开 `POST /subscription/portal` 返回的 Stripe Customer Portal。
- `/subscription/cancel` 仍保留，用于历史本地订阅或无门户路径时的安全取消。
- 如果本地订阅带 `stripe_subscription_id`，后端必须先调用 Stripe API 取消远端订阅；缺少 `STRIPE_SECRET_KEY` 时拒绝本地降级，避免远端继续扣费。

## 五、前端边界

- `src/api/subscription.ts` 只调用后端接口，不引入 Stripe SDK。
- `useSubscription.changeTo()` 对付费套餐调用 `createCheckout()` 并跳转 `checkoutUrl`。
- `useSubscription.cancel()` 优先调用 `openBillingPortal()`，失败后才走本地取消确认。
- `/pricing?billing=cancel` 只提示用户取消了托管结账。
- `/user?billing=success` 只触发重新拉取订阅 / 用量 / 发票，不直接假设支付成功。

## 六、部署与验收

上线 Stripe 收费前必须完成：

1. 后端 `.env` 配置 `STRIPE_SECRET_KEY`、`STRIPE_WEBHOOK_SECRET`、`FRONTEND_BASE_URL`。
2. Stripe 控制台 Webhook 指向 `{后端域名}/webhooks/stripe`。
3. 管理员对 Pro / Team 调用 `POST /admin/plans/{code}/sync`，确认对应 Price ID 已回填。
4. 前端点击付费套餐后跳转 Stripe Checkout。
5. 支付完成返回 `/user?billing=success` 后，等待 Webhook 回写，再确认 `/subscription` 显示付费套餐。
6. Stripe 控制台重放同一 Webhook 事件，本地不应新增重复订阅或重复发票。
7. Customer Portal 能打开并返回 `/user`。

未完成以上配置时，付费切换应失败并提示缺少 Stripe 配置，不允许本地直接升级付费套餐。
