import re
import bcrypt
from app.core.config import settings
pw_max_length = settings.pw_max_length
pw_min_length = settings.pw_min_length
_has_letter = re.compile(r"[a-zA-Z]")
_has_digit = re.compile(r"\d")
_bcrypt_max_bytes = 72
bcrypt_rounds = 12
#密码哈希
def hash_password(raw_password:str)->str:
    raw = raw_password.encode("utf-8")[:_bcrypt_max_bytes]
    return bcrypt.hashpw(raw, bcrypt.gensalt(bcrypt_rounds)).decode("ascii")
#校验密码
def check_password(raw_password:str,hashed_password:str)->bool:
    raw = raw_password.encode("utf-8")[:_bcrypt_max_bytes]
    try:
        return bcrypt.checkpw(raw, hashed_password.encode("ascii"))
    except (ValueError,TypeError):
        return False
#校验密码强度
def check_password_strength(raw_password:str)->bool:
    if not pw_min_length<=len(raw_password)<=pw_max_length:
        raise ValueError(f"密码长度必须在{pw_min_length}到{pw_max_length}之间")
    if not _has_letter.search(raw_password) and not _has_digit.search(raw_password):
        raise ValueError(f"密码必须包含字母或数字")
    return True
