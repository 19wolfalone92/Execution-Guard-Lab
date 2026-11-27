from integrated.core.src.key_rotation import valid_internal_key

def test_rotation():
    a,b='a'*32,'b'*32
    assert valid_internal_key(a,a) and not valid_internal_key(b,a)
    assert valid_internal_key(a,b,a) and valid_internal_key(b,b,a)
    assert not valid_internal_key(a,b) and valid_internal_key(b,b)
    assert not valid_internal_key(a,None,a) and not valid_internal_key('short',b,'short')
