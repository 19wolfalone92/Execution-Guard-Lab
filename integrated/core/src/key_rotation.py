import hmac

def valid_internal_key(actual,current,previous=None):
    # Previous is optional and accepted only during explicitly staged rotation.
    if not isinstance(current,str) or len(current)<32 or not isinstance(actual,str):return False
    current_ok=hmac.compare_digest(actual.encode(),current.encode())
    old_ok=isinstance(previous,str) and len(previous)>=32 and previous!=current and hmac.compare_digest(actual.encode(),previous.encode())
    return current_ok or old_ok
