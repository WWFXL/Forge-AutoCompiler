"""恢复阶段的有界容器查询；不执行模型提供的Shell，不替代Workflow修复。"""

from __future__ import annotations

import json
import shlex
import time
from typing import Literal

from langchain_core.tools import tool

from deerflow.compile.plan_workflow import PlanContractError, PlanStep

DIAGNOSTIC_VERSION = "recovery-environment-v2"
RECOVERY_ENVIRONMENT_PROMPT = """
恢复时可用search_build_files与inspect_build_environment查询实际编译容器，不局限于原源码。
遇到未定义宏、缺头文件/库/命令：沿“缺失项→提供文件/组件→开发包→安装/路径”获取证据。已安装目录搜索不能发现未安装包的内容。
package_search搜索包名及描述，可用相关工具/组件名发现名称不同的开发包，再用package_description核实用途。
已知缺失文件名时，package_file_search查文件提供包；它不搜索宏或符号的内容。owner只查已安装文件所属包，不能替代未安装包检索。
APT查询返回index_state；索引缺失时，空结果或无候选不代表仓库没有该包。若需准备，将apt-get update写入dependency步骤由Workflow执行。
文件查询工具/Contents索引不可用时，明确缺少的查询能力；必要时将安装apt-file及apt-file update写入准备步骤，不把不可用当作无提供者。
准备后的索引仍只覆盖已配置软件源/架构；package_index(query="apt")可单独检查。command查询只接受工具名，例如aclocal，不接受整条Shell命令。
区分未安装、已安装但路径未生效和有证据支持的版本不兼容；无命中或查询不可用不证明版本移除了功能。
优先采用系统包及正确路径的最小修复；仅在查询证据支持系统包不能满足时考虑源码安装依赖。
不要重复分段读取同一文件猜测，也不要伪造宏或跳过依赖检查。诊断有次数与时间限制，证据足够即返回完整修订方案。
查询不会安装依赖、修改构建阶段或证明构建成功；安装/环境修复仍写入dependency/configure步骤由Workflow执行。
"""

# 在实际编译容器中运行的固定程序。所有模型输入仅为JSON数据；不解释Shell或正则。
QUERY_PROGRAM = r"""
import glob,json,os,pathlib,re,selectors,shutil,subprocess,time
cfg=CONFIG
started=time.monotonic()
limit=8000
query_seconds=20 if cfg.get('kind')=='package_file_search' else 8
safe_path='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
def run(argv):
    executable=shutil.which(argv[0],path=safe_path)
    if not executable:
        return dict(status='unavailable',command=argv[0],reason='查询工具未安装；未执行索引更新或安装')
    env=dict(os.environ,LC_ALL='C',PATH=safe_path)
    p=subprocess.Popen([executable,*argv[1:]],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env,start_new_session=True)
    chunks=[]; size=0; truncated=False; timed_out=False
    with selectors.DefaultSelector() as selector:
        selector.register(p.stdout,selectors.EVENT_READ)
        while selector.get_map():
            if time.monotonic()-started>query_seconds:
                timed_out=True; break
            for key,_ in selector.select(.1):
                data=os.read(key.fd,1024)
                if not data:
                    selector.unregister(key.fileobj); continue
                chunks.append(data); size+=len(data)
                if size>=limit:
                    truncated=True; break
            if truncated: break
    if truncated or timed_out:
        import signal
        try: os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError: pass
    code=p.wait(timeout=2)
    p.stdout.close()
    output=b''.join(chunks)[:limit].decode('utf-8','replace')
    status='timeout' if timed_out else 'truncated' if truncated else 'ok' if code==0 else 'query_failed'
    return dict(status=status,argv=argv,executable=executable,exit_code=code,output=output,truncated=truncated)

def index_state():
    root=pathlib.Path('/var/lib/apt/lists')
    packages=[p for p in root.glob('*_Packages*') if p.is_file()]
    contents=[p for p in root.glob('*_Contents-*') if p.is_file()]
    return dict(package_indexes=len(packages),contents_indexes=len(contents),
                packages='present' if packages else 'missing',
                contents='present' if contents else 'missing',
                apt_file_available=shutil.which('apt-file',path=safe_path) is not None,
                coverage='仅当前本地索引；present不证明最新或覆盖全部源/架构',
                preparation='缺包索引时在dependency步骤运行apt-get update；缺文件查询能力时安装apt-file并运行apt-file update')

if cfg['operation']=='search':
    scope=cfg['scope']; query=cfg['query']
    roots={
      'project':['/workspace/repo'],
      'macros':glob.glob('/usr/share/aclocal*')+glob.glob('/usr/local/share/aclocal*'),
      'headers':['/usr/include','/usr/local/include'],
      'pkgconfig':glob.glob('/usr/lib/*/pkgconfig')+['/usr/lib/pkgconfig','/usr/share/pkgconfig','/usr/local/lib/pkgconfig','/usr/local/share/pkgconfig'],
      'dependencies':['/workspace/dependencies'],
    }[scope]
    roots=[pathlib.Path(r).resolve() for r in roots if pathlib.Path(r).is_dir()]
    matches=[]; files=0; size=0; stopped=False; skipped=False; seen=set(); errors=[]
    for root in roots:
        for directory,dirs,names in os.walk(root,followlinks=False,onerror=lambda error: errors.append(str(error))):
            dirs[:]=sorted(d for d in dirs if not d.startswith('.') and not (pathlib.Path(directory)/d).is_symlink())
            for name in sorted(names):
                if time.monotonic()-started>5 or files>=2000 or size>=16000000 or len(matches)>=20:
                    stopped=True; break
                path=pathlib.Path(directory)/name
                if name.startswith('.') or path.is_symlink() or not path.is_file(): continue
                resolved=path.resolve()
                if not resolved.is_relative_to(root) or resolved in seen: continue
                seen.add(resolved)
                if scope=='macros' and path.suffix!='.m4': continue
                if scope=='pkgconfig' and path.suffix!='.pc': continue
                files+=1
                try:
                    if path.stat().st_size>1000000:
                        skipped=True; continue
                    data=path.read_bytes(); size+=len(data)
                    if b'\0' in data: continue
                    for number,line in enumerate(data.decode('utf-8','replace').splitlines(),1):
                        if query in line:
                            matches.append(dict(path=str(path),line=number,text=line[:300]))
                            if len(matches)>=20:
                                stopped=True; break
                except OSError: skipped=True
            if stopped: break
        if stopped: break
    result=dict(status='matches' if matches else 'no_match_in_scope' if roots else 'unavailable',scope=scope,roots=[str(p) for p in roots],matches=matches,files_scanned=files,bytes_scanned=size,incomplete=stopped or skipped or bool(errors),
                note='仅搜索已存在的限定目录；空结果不能证明包不存在或功能已移除')
else:
    kind=cfg['kind']; q=cfg['query']
    if kind=='command': result=run([q,'--version'])
    elif kind=='package':
        result=run(['dpkg-query','-W','-f=${binary:Package}\t${db:Status-Abbrev}\t${Version}\n',q])
        if result['status']=='ok':
            fields=result['output'].rstrip('\n').split('\t')
            state=fields[1].strip() if len(fields)>1 else ''
            result.update(package_state=state,installed=state=='ii',version=fields[2] if len(fields)>2 else '')
        elif result['status']=='query_failed': result['installed']=False
    elif kind=='package_index': result=dict(status='ok',index_state=index_state())
    elif kind=='package_policy': result=run(['apt-cache','policy',q])
    elif kind=='package_description': result=run(['apt-cache','show',q])
    elif kind=='package_files': result=run(['dpkg-query','-L',q])
    elif kind=='owner': result=run(['dpkg-query','-S',q])
    elif kind=='package_search':
        result=run(['apt-cache','search',re.escape(q)])
        result['match_scope']='package_name_and_description'
    elif kind=='package_file_search':
        result=run(['apt-file','search','--regexp',r'(^|/)'+re.escape(q.lstrip('/'))+'$'])
        if result['status']=='query_failed' and result.get('exit_code')==1 and index_state()['contents']=='present':
            result['status']='no_match_in_index'
        elif result['status']=='query_failed':
            result['status']='unavailable'
            result['reason']='文件索引查询失败（可能无索引）；不能据此认定文件无提供者'
    elif kind=='search_paths':
        result=run({'aclocal':['aclocal','--print-ac-dir'],'pkg-config':['pkg-config','--variable=pc_path','pkg-config'],'cc':['cc','-print-search-dirs']}[q])
        result['environment']={key:os.environ.get(key,'') for key in ('ACLOCAL_PATH','PKG_CONFIG_PATH','CMAKE_PREFIX_PATH','CPATH','LIBRARY_PATH','LD_LIBRARY_PATH')}
    else: raise ValueError('unknown query')
    if kind in {'package_policy','package_description','package_search','package_file_search'}:
        result['index_state']=index_state()
        result['evidence_scope']='当前可见包/文件索引，空结果不证明不存在或版本移除'
        if result.get('status')=='ok' and not result.get('output','').strip():
            result['status']='no_match_in_index' if result['index_state']['packages']=='present' else 'index_unavailable'
print(json.dumps(result,ensure_ascii=False))
"""

SearchScope = Literal["project", "macros", "headers", "pkgconfig", "dependencies"]
EnvironmentKind = Literal["command", "package", "package_policy", "package_description", "package_files", "owner", "package_search", "package_file_search", "package_index", "search_paths"]
COMMANDS = {"aclocal", "autoconf", "automake", "autoreconf", "libtool", "libtoolize", "m4", "make", "cmake", "ninja", "gcc", "g++", "cc", "c++", "pkg-config", "python3", "makeinfo", "meson"}


def query_command(operation, query, *, scope=None, kind=None):
    """验证结构化输入并生成固定查询脚本；原始输入从不拼成Shell。"""
    if not isinstance(query, str) or not query.strip() or len(query) > 160 or any(ord(c) < 32 for c in query):
        raise ValueError("查询必须为1–160字符的单行名称或路径")
    if operation == "search":
        if scope not in SearchScope.__args__:
            raise ValueError("不支持的搜索范围")
    elif operation == "environment":
        if kind not in EnvironmentKind.__args__:
            raise ValueError("不支持的环境查询")
        if query.startswith("-"):
            raise ValueError("查询不能是命令选项")
        if kind == "command" and query not in COMMANDS:
            raise ValueError("只允许查询常见构建工具的版本")
        if kind == "search_paths" and query not in {"aclocal", "pkg-config", "cc"}:
            raise ValueError("路径查询只支持aclocal、pkg-config、cc")
        if kind == "package_index" and query != "apt":
            raise ValueError("索引状态查询只接受apt")
        if kind in {"package", "package_policy", "package_description", "package_files"}:
            import re

            if not re.fullmatch(r"[a-z0-9][a-z0-9+.:-]*", query):
                raise ValueError("需要精确的软件包名称，不接受通配符或选项")
        if kind == "owner" and not query.startswith(("/usr/", "/lib/", "/lib64/", "/bin/", "/sbin/")):
            raise ValueError("owner仅查询系统开发文件路径")
        if kind == "owner" and (".." in query.split("/") or any(c in query for c in "*?[]")):
            raise ValueError("owner需要精确路径，不接受上溯或通配符")
    else:
        raise ValueError("不支持的查询操作")
    config = dict(operation=operation, query=query, scope=scope, kind=kind)
    return "python3 -c " + shlex.quote(QUERY_PROGRAM.replace("CONFIG", repr(config), 1))


class RecoveryEnvironment:
    """绑定一次活动恢复交接，沿用原执行通道、命令总额、日志和源码保护。"""

    def __init__(self, workflow, meter, *, diagnostic_memory=None):
        self.workflow, self.meter = workflow, meter
        self.diagnostic_memory = diagnostic_memory
        self.handoff_id = workflow.handoff["handoff_id"]
        self.calls = 0

    def execute(self, operation, query, **kwargs):
        try:
            command = query_command(operation, query, **kwargs)
        except ValueError as exc:
            return dict(status="invalid_query", reason=str(exc))
        w = self.workflow
        with w.manager.session_lock(w.thread_id, w.session_id):
            w._observe()
            if w.status != "needs_handoff" or not w.handoff or w.handoff["handoff_id"] != self.handoff_id:
                raise PlanContractError("诊断工具只允许用于当前活动恢复交接")
            if self.calls >= 12 or w.commands_used >= w.budget.max_commands:
                return dict(status="budget_exhausted", reason="诊断次数或任务命令预算耗尽；请利用已有证据返回方案")
            self.meter.tracker.observe_elapsed(time.monotonic() - self.meter.started_monotonic)
            remaining = min(w._remaining(), self.meter.tracker.remaining().node_seconds)
            if remaining < 1:
                raise PlanContractError("诊断前主任务时间已耗尽")
            self.meter.tracker.consume(commands=1)
            self.calls += 1
            w.commands_used += 1
            step = PlanStep(step_id="recovery-query", role="build", command=command, source=DIAGNOSTIC_VERSION, expected="查询实际容器证据").model_copy(update={"role": "diagnostic"})
            started = time.monotonic()
            try:
                query_limit = 25 if kwargs.get("kind") == "package_file_search" else 15
                record, output = w._post_command(step, min(query_limit, w.budget.command_timeout_seconds, int(remaining)))
                try:
                    result = json.loads(output.stdout) if record.exit_code == 0 else dict(status="query_failed", output=output.combined_output[-2000:])
                except ValueError:
                    result = dict(status="query_failed", output=output.combined_output[-2000:])
                result.update(command_id=record.command_id, exit_code=record.exit_code, timed_out=record.timed_out, log_path="logs/" + record.command_id + ".log")
                self.meter.ledger.append("recovery.environment_query", version=DIAGNOSTIC_VERSION, handoff_id=self.handoff_id, operation=operation, query=query, **kwargs, result=result)
                return result
            finally:
                w.timings["recovery_diagnostic_seconds"] = w.timings.get("recovery_diagnostic_seconds", 0) + time.monotonic() - started
                w.handoff["command_frontier"] = w._expected_frontier
                w._persist()

    def tools(self):
        @tool
        def search_build_files(query: str, scope: SearchScope = "project") -> str:
            """按精确文本搜索容器项目、系统宏/头文件/pkgconfig或外部依赖；返回文件行号和有界片段。空结果不代表包不存在。"""
            return json.dumps(self.execute("search", query, scope=scope), ensure_ascii=False)

        @tool
        def inspect_build_environment(kind: EnvironmentKind, query: str) -> str:
            """查询版本、包状态/候选/描述/文件/所属包、包名及描述搜索、文件提供者和索引状态。package_index传apt；package_file_search传文件名而非符号。不安装或更新索引。"""
            return json.dumps(self.execute("environment", query, kind=kind), ensure_ascii=False)

        return [search_build_files, inspect_build_environment]
