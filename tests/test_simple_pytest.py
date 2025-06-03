def test_basic():
    """最基本的pytest测试"""
    assert 1 + 1 == 2

def test_import_basic():
    """测试基本导入"""
    import os
    assert os.path.exists('.')