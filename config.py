from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Match these exactly to your .env keys
    db_host: str
    db_port: str
    db_user: str
    db_password: str
    db_name: str
    
    gemini_api_key: str
    openai_api_key: str
    
    # Cloud/AWS (Required by your Task 1.1 instructions)
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str
    s3_bucket_name: str
    
    # Logic: Allow extra fields so OpenAI/AWS keys don't crash the app
    model_config = SettingsConfigDict(
        env_file=".env", 
        extra="ignore",  # Important: Stop the 'Extra inputs' error
        case_sensitive=False
    )

settings = Settings()