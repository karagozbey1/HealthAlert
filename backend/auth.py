from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Ilk bcrypt dogrulamasinda backend yukleme hatasini onler.
try:
    from passlib.handlers.bcrypt import bcrypt as _bcrypt_cls  # type: ignore
    _bcrypt_cls.set_backend("bcrypt")
except Exception:
    pass

# Bcrypt ile şifre doğrular.
def verify_password(plain: str, hashed: str) -> bool:
    """Girilen parolayı saklanan hash değeriyle karşılaştırır."""
    return pwd_context.verify(plain, hashed)

# Bcrypt ile şifreyi hashler.
def hash_password(plain: str) -> str:
    """Kullanıcı parolasını veritabanında saklanacak hash değerine çevirir."""
    return pwd_context.hash(plain)

# JWT erişim tokeni üretir.
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Kullanıcı oturumu için süreli JWT erişim tokenı üretir."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

# JWT tokeni çözümler ve payload döndürür.
def decode_token(token: str) -> Optional[dict]:
    """JWT erişim tokenını doğrulayıp içindeki kullanıcı bilgisini çözer."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
