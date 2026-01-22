# build.py
# !/usr/bin/env python3
"""
打包脚本 - 使用 PyInstaller 打包程序
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path


class Builder:
    def __init__(self):
        self.app_name = "IPAnalyzer"
        self.version = "1.0.0"
        self.company = "Mingxin Tools"

        # 目录设置
        self.root_dir = Path(__file__).parent
        self.build_dir = self.root_dir / "build"
        self.dist_dir = self.root_dir / "dist"
        self.spec_dir = self.root_dir

        # 图标文件
        self.icon_file = self.root_dir / "icon.ico"

    def cleanup(self):
        """清理构建目录"""
        print("清理构建目录...")
        for dir_path in [self.build_dir, self.dist_dir]:
            if dir_path.exists():
                shutil.rmtree(dir_path)
                print(f"✓ 已清理: {dir_path}")

        # 清理临时文件
        for pattern in ["*.spec", "*.log"]:
            for file in self.root_dir.glob(pattern):
                try:
                    file.unlink()
                    print(f"✓ 已删除: {file}")
                except:
                    pass

    def create_icon(self):
        """创建图标文件（如果不存在）"""
        if not self.icon_file.exists():
            print("创建图标文件...")
            try:
                # 使用PIL创建简单图标
                from PIL import Image, ImageDraw, ImageFont

                # 创建64x64图标
                img = Image.new('RGBA', (64, 64), (66, 133, 244, 255))
                draw = ImageDraw.Draw(img)

                # 添加文字
                try:
                    font = ImageFont.truetype("arial.ttf", 24)
                except:
                    font = ImageFont.load_default()

                # 绘制"IP"文字
                draw.text((32, 32), "IP", font=font, fill=(255, 255, 255, 255),
                          anchor="mm")

                # 保存为ICO
                img.save(self.icon_file, format='ICO')
                print(f"✓ 图标已创建: {self.icon_file}")
            except Exception as e:
                print(f"✗ 创建图标失败: {e}")
                # 使用默认图标
                self.icon_file = None
        else:
            print(f"✓ 使用现有图标: {self.icon_file}")

    def collect_requirements(self):
        """收集依赖包"""
        print("收集依赖包...")

        # 创建requirements.txt
        requirements = [
            "PyQt6>=6.5.0",
            "requests>=2.31.0",
            "pyperclip>=1.8.2",
            "plyer>=2.1.0",
            "win10toast>=0.9",
            "Pillow>=10.0.0",  # 用于图标处理
            "winshell>=0.6",  # 用于快捷方式
            "pywin32>=305"  # 用于Windows API
        ]

        with open(self.root_dir / "requirements.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(requirements))

        print("✓ 依赖列表已生成")

        # 安装依赖（可选）
        install = input("是否安装依赖包？(y/n): ").lower()
        if install == 'y':
            subprocess.run([sys.executable, "-m", "pip", "install"] + requirements)
            print("✓ 依赖包已安装")

    def build_exe(self):
        """使用PyInstaller构建可执行文件"""
        print("开始构建可执行文件...")

        # PyInstaller命令参数
        args = [
            sys.executable, "-m", "PyInstaller",
            "--onefile",  # 单文件
            "--windowed",  # 无控制台窗口
            f"--name={self.app_name}",
            "--clean",  # 清理临时文件
            "--noconfirm",  # 覆盖输出目录不提示
        ]

        # 添加图标
        if self.icon_file and self.icon_file.exists():
            args.append(f"--icon={self.icon_file}")

        # 添加版本信息
        version_info = f"""
# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({1}, 0, 0, 0),
    prodvers=({1}, 0, 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'040904B0',
          [StringStruct(u'CompanyName', u'{self.company}'),
           StringStruct(u'FileDescription', u'{self.app_name}'),
           StringStruct(u'FileVersion', u'{self.version}'),
           StringStruct(u'InternalName', u'{self.app_name}'),
           StringStruct(u'LegalCopyright', u'Copyright © 2025 {self.company}'),
           StringStruct(u'OriginalFilename', u'{self.app_name}.exe'),
           StringStruct(u'ProductName', u'{self.app_name}'),
           StringStruct(u'ProductVersion', u'{self.version}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""

        # 创建版本信息文件
        version_file = self.root_dir / "version_info.txt"
        with open(version_file, "w", encoding="utf-8") as f:
            f.write(version_info)

        args.append(f"--version-file=version_info.txt")

        # 添加数据文件
        args.extend([
            "--add-data", f"config.py;.",
            "--add-data", f"README.md;." if (self.root_dir / "README.md").exists() else "",
        ])

        # 排除不需要的模块
        args.extend([
            "--exclude-module", "matplotlib",
            "--exclude-module", "numpy",
            "--exclude-module", "scipy",
            "--exclude-module", "pandas",
        ])

        # 隐藏导入
        args.extend([
            "--hidden-import", "PyQt6.QtCore",
            "--hidden-import", "PyQt6.QtWidgets",
            "--hidden-import", "PyQt6.QtGui",
            "--hidden-import", "plyer.platforms.win.notification",
            "--hidden-import", "win10toast",
            "--hidden-import", "pyperclip",
        ])

        # 主程序文件
        args.append("main.py")

        # 执行构建
        print("执行命令:", " ".join(args))
        result = subprocess.run(args, capture_output=True, text=True)

        if result.returncode == 0:
            print("✓ 构建成功！")

            # 显示输出文件信息
            exe_path = self.dist_dir / f"{self.app_name}.exe"
            if exe_path.exists():
                size = exe_path.stat().st_size / (1024 * 1024)  # MB
                print(f"输出文件: {exe_path}")
                print(f"文件大小: {size:.2f} MB")
        else:
            print("✗ 构建失败:")
            print(result.stderr)

        # 清理版本信息文件
        if version_file.exists():
            version_file.unlink()

    def create_installer(self):
        """创建安装包"""
        print("\n创建安装包...")

        # 创建安装包目录结构
        installer_dir = self.root_dir / "installer"
        installer_dir.mkdir(exist_ok=True)

        # 复制文件到安装包目录
        files_to_copy = [
            (self.dist_dir / f"{self.app_name}.exe", installer_dir / f"{self.app_name}.exe"),
            (self.root_dir / "installer.py", installer_dir / "installer.py"),
            (self.root_dir / "README.md", installer_dir / "README.md") if (
                        self.root_dir / "README.md").exists() else None,
            (self.root_dir / "LICENSE", installer_dir / "LICENSE") if (self.root_dir / "LICENSE").exists() else None,
        ]

        for src, dst in files_to_copy:
            if src and src.exists():
                shutil.copy2(src, dst)
                print(f"✓ 复制: {src.name}")

        # 创建NSIS安装脚本
        self.create_nsis_script(installer_dir)

        # 如果安装了NSIS，可以自动编译
        if shutil.which("makensis"):
            print("检测到NSIS，正在编译安装程序...")
            nsis_script = installer_dir / "installer.nsi"
            subprocess.run(["makensis", str(nsis_script)], check=True)
            print("✓ 安装程序编译完成")

        print(f"安装文件位于: {installer_dir}")

    # build.py 中的 create_nsis_script 方法需要修改编码：

    def create_nsis_script(self, installer_dir):
        """创建NSIS安装脚本（使用UTF-8 with BOM）"""
        nsis_content = """ ; NSIS安装脚本 - UTF-8 with BOM 编码
    Unicode true
    ManifestDPIAware true

    ; 基本信息
    !define APP_NAME "IPAnalyzer"
    !define APP_VERSION "1.0.0"
    !define APP_PUBLISHER "Mingxin Tools"
    !define APP_EXE "${APP_NAME}.exe"
    !define UNINSTALLER_NAME "Uninstall_${APP_NAME}.exe"

    ; 压缩设置
    SetCompressor /SOLID lzma
    SetCompressorDictSize 32

    ; 安装程序名称
    Name "${APP_NAME}"
    OutFile "${APP_NAME}_Setup_v${APP_VERSION}.exe"
    InstallDir "$PROGRAMFILES\\${APP_PUBLISHER}\\${APP_NAME}"

    ; 界面设置
    !include "MUI2.nsh"
    !define MUI_ABORTWARNING
    !define MUI_ICON "${NSISDIR}\\Contrib\\Graphics\\Icons\\modern-install.ico"
    !define MUI_UNICON "${NSISDIR}\\Contrib\\Graphics\\Icons\\modern-uninstall.ico"

    ; 安装向导页面
    !insertmacro MUI_PAGE_WELCOME
    !insertmacro MUI_PAGE_DIRECTORY
    !insertmacro MUI_PAGE_INSTFILES
    !insertmacro MUI_PAGE_FINISH

    ; 卸载向导页面
    !insertmacro MUI_UNPAGE_CONFIRM
    !insertmacro MUI_UNPAGE_INSTFILES

    ; 语言设置
    !insertmacro MUI_LANGUAGE "SimpChinese"

    ; 默认安装段
    Section "主程序" MainSection
        SetOutPath "$INSTDIR"

        ; 复制文件
        File "${__FILEDIR__}\\${APP_EXE}"

        ; 创建卸载程序
        WriteUninstaller "$INSTDIR\\${UNINSTALLER_NAME}"

        ; 创建开始菜单快捷方式
        CreateDirectory "$SMPROGRAMS\\${APP_PUBLISHER}\\${APP_NAME}"
        CreateShortCut "$SMPROGRAMS\\${APP_PUBLISHER}\\${APP_NAME}\\${APP_NAME}.lnk" "$INSTDIR\\${APP_EXE}"
        CreateShortCut "$SMPROGRAMS\\${APP_PUBLISHER}\\${APP_NAME}\\卸载 ${APP_NAME}.lnk" "$INSTDIR\\${UNINSTALLER_NAME}"

        ; 创建桌面快捷方式
        CreateShortCut "$DESKTOP\\${APP_NAME}.lnk" "$INSTDIR\\${APP_EXE}"

        ; 写入注册表信息
        WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APP_NAME}" "DisplayName" "${APP_NAME}"
        WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APP_NAME}" "UninstallString" '"$INSTDIR\\${UNINSTALLER_NAME}"'
        WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APP_NAME}" "DisplayIcon" "$INSTDIR\\${APP_EXE}"
        WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APP_NAME}" "DisplayVersion" "${APP_VERSION}"
        WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APP_NAME}" "Publisher" "${APP_PUBLISHER}"
        WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APP_NAME}" "InstallLocation" "$INSTDIR"
        WriteRegDWORD HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APP_NAME}" "NoModify" 1
        WriteRegDWORD HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APP_NAME}" "NoRepair" 1
    SectionEnd

    ; 卸载段
    Section "Uninstall"
        ; 停止程序（如果正在运行）
        ExecWait '"$INSTDIR\\${APP_EXE}" --quit'

        ; 删除文件
        Delete "$INSTDIR\\${APP_EXE}"
        Delete "$INSTDIR\\${UNINSTALLER_NAME}"
        RMDir "$INSTDIR"

        ; 删除开始菜单快捷方式
        Delete "$SMPROGRAMS\\${APP_PUBLISHER}\\${APP_NAME}\\${APP_NAME}.lnk"
        Delete "$SMPROGRAMS\\${APP_PUBLISHER}\\${APP_NAME}\\卸载 ${APP_NAME}.lnk"
        RMDir "$SMPROGRAMS\\${APP_PUBLISHER}\\${APP_NAME}"
        RMDir "$SMPROGRAMS\\${APP_PUBLISHER}"

        ; 删除桌面快捷方式
        Delete "$DESKTOP\\${APP_NAME}.lnk"

        ; 删除注册表信息
        DeleteRegKey HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APP_NAME}"
    SectionEnd
    """

        nsis_file = installer_dir / "installer.nsi"

        # 使用UTF-8 with BOM编码保存
        with open(nsis_file, 'wb') as f:
            # 写入BOM头
            f.write(b'\xEF\xBB\xBF')
            f.write(nsis_content.encode('utf-8'))

        print(f"✓ NSIS脚本已创建: {nsis_file}")

    def build(self):
        """执行完整构建流程"""
        print(f"开始构建 {self.app_name} v{self.version}")
        print("=" * 50)

        steps = [
            ("清理构建目录", self.cleanup),
            ("创建图标文件", self.create_icon),
            ("收集依赖包", self.collect_requirements),
            ("构建可执行文件", self.build_exe),
            ("创建安装包", self.create_installer),
        ]

        for step_name, step_func in steps:
            print(f"\n{step_name}...")
            try:
                step_func()
            except Exception as e:
                print(f"✗ {step_name}失败: {e}")
                if input("是否继续？(y/n): ").lower() != 'y':
                    break

        print("\n" + "=" * 50)
        print("构建流程完成！")
        print("\n下一步：")
        print("1. 运行 dist\\剪贴板IP地理分析工具.exe 测试程序")
        print("2. 使用 installer\\installer.nsi 编译安装程序")
        print("3. 分发 剪贴板IP地理分析工具_Setup_v1.0.0.exe")


if __name__ == "__main__":
    builder = Builder()
    builder.build()