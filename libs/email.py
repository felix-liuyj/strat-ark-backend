"""Async email controller based on aiosmtplib."""

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from aiosmtplib import SMTP, SMTPException

from configs import get_settings

__all__ = ("EmailController",)

_logger = logging.getLogger(__name__)


class EmailController(SMTP):
    def __init__(
        self,
        from_email: str,
        to_email: str,
        subject: str,
        email_body: str,
        use_tls: bool = False,
    ) -> None:
        super().__init__(
            hostname=get_settings().SMTP_HOST,
            port=get_settings().SMTP_PORT,
            use_tls=use_tls,
        )
        self.from_email = from_email
        self.to_email = to_email
        self.subject = subject
        self.email_body = email_body
        self.message = self._generate_email_message()

    async def send_email_with_ssl(self) -> bool:
        try:
            await self.connect()
            await self.login(get_settings().SMTP_USERNAME, get_settings().SMTP_PASSWORD)
            await self.sendmail(self.from_email, self.to_email, self.message.as_string())
            await self.quit()
            return True
        except SMTPException:
            _logger.exception("SMTP send failed")
            return False

    def _generate_email_message(self) -> MIMEMultipart:
        message = MIMEMultipart("alternative")
        message["From"] = self.from_email
        message["To"] = self.to_email
        message["Subject"] = self.subject
        message.attach(MIMEText(self.email_body, "html"))
        return message
