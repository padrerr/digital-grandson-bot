from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    BOT_TOKEN: str
    ADMIN_IDS: str = ""
    GIGACHAT_CREDENTIALS: str = ""
    GPT2GIGA_API_KEY: str = "mysecretkey123"
    GPT2GIGA_URL: str = "http://localhost:8090/v1"
    DB_URL: str = "sqlite+aiosqlite:///data/bot.db"

    REMINDER_AFTER_MIN: int = 3
    WELLBEING_AFTER_HOURS: int = 4

    EVENING_REPORT_HOUR: int = 21
    EVENING_REPORT_MINUTE: int = 0

    BIRTHDAY_HOUR: int = 10
    BIRTHDAY_MINUTE: int = 0

    WELLBEING_REMINDER_MIN: int = 10
    WELLBEING_ALERT_MIN: int = 15

    WHISPER_MODEL: str = "tiny"

    MAX_FAMILY_MEMBERS: int = 5
    MAX_ELDERLY_PER_FAMILY: int = 5

    @property
    def admin_ids(self) -> list[int]:
        return [int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip()]


settings = Settings()