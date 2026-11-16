已验证错误经验（按错误与环境适用，不按项目名）：
若Autotools报LT_SYS_SYMBOL_USCORE未定义，先核实ltdl宏提供者。已验证Ubuntu包libltdl-dev 2.4.7-7build1提供/usr/share/aclocal/ltdl.m4及该宏；仅装libtool可能缺它，不能推断新版删宏。
在Debian/Ubuntu先用diagnose_dependency(kind="macro", item="LT_SYS_SYMBOL_USCORE", candidate="libltdl-dev")核实包/安装/路径，必要时以package_file_search查ltdl.m4。缺包则在修订dependency步骤安装：apt-get install -y --no-install-recommends libltdl-dev；已装则核实宏文件及aclocal搜索路径。修复后重跑原配置生成、配置和构建。其他发行版先查提供包；不把全部未定义宏套用此包，不用固定检测值替代真实宏。
