from app.tools.env_check import check_python, check_sqlite, check_torch_cuda, check_ultralytics


def test_env_check_no_crash():
    # Just ensure the functions can be called and return expected types
    assert isinstance(check_python(), str)
    
    torch_ver, cuda = check_torch_cuda()
    assert isinstance(torch_ver, str)
    assert isinstance(cuda, bool)
    
    assert isinstance(check_ultralytics(), str)
    
    sqlite_ver, fts5 = check_sqlite()
    assert isinstance(sqlite_ver, str)
    assert isinstance(fts5, bool)
