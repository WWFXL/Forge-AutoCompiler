"""任务作者的CMake功能与实际CTest检查；不以缓存类型格式替代功能义务。"""

from __future__ import annotations

import shlex


def cmake_configuration_command(requirements: dict[str, bool], *, default_static: bool = True) -> str:
    script = f"""from pathlib import Path
cache={{}}
for line in Path('build/CMakeCache.txt').read_text().splitlines():
 if '=' in line and ':' in line and not line.startswith(('//','#')):
  key,value=line.split('=',1); name,_=key.split(':',1); cache[name]=value
false_values={{'','0','OFF','NO','FALSE','N','IGNORE','NOTFOUND'}}
def enabled(value):
 return value.upper() not in false_values and not value.upper().endswith('-NOTFOUND')
requirements={requirements!r}
for key,expected in requirements.items():
 assert key in cache, '缺少必要配置:'+key
 assert enabled(cache[key])==expected, '配置功能不符:'+key+'='+cache[key]
if {default_static!r}:
 assert not enabled(cache.get('BUILD_SHARED_LIBS','OFF')), '必须使用默认静态库构建'
print('FORGE_TASK_CONFIGURATION_OK')
"""
    return "python3 -c " + shlex.quote(script)


def ctest_execution_command(expected_tests: int) -> str:
    if expected_tests < 1:
        raise ValueError("固定作者测试必须非空")
    script = f"""import xml.etree.ElementTree as ET
root=ET.parse('/workspace/forge-ctest.xml').getroot()
cases=list(root.iter('testcase'))
assert len(cases)=={expected_tests}, '作者注册测试数不符'
assert all(c.find('skipped') is None and c.find('failure') is None and c.find('error') is None for c in cases), '存在跳过或失败的作者测试'
assert all(c.get('status','run')=='run' for c in cases), '存在未实际运行测试'
print('FORGE_CTEST_ACTUALLY_PASSED='+str(len(cases)))
"""
    return "python3 -c " + shlex.quote(script)
