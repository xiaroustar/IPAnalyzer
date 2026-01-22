#!/usr/bin/env python3
"""
IP Analyzer 打包脚本
将Python程序打包为单个EXE文件
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path


def setup_virtual_env():
    """设置虚拟环境"""
    print("正在设置虚拟环境...")

    venv_dir = "venv"
    if not os.path.exists(venv_dir):
        try:
            subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True)
            print("✓ 虚拟环境创建成功")
        except subprocess.CalledProcessError:
            print("✗ 虚拟环境创建失败")
            return None

    # 获取虚拟环境的Python路径
    if sys.platform == "win32":
        python_path = os.path.join(venv_dir, "Scripts", "python.exe")
        pip_path = os.path.join(venv_dir, "Scripts", "pip.exe")
    else:
        python_path = os.path.join(venv_dir, "bin", "python")
        pip_path = os.path.join(venv_dir, "bin", "pip")

    return python_path, pip_path


def install_dependencies(pip_path):
    """安装依赖包"""
    print("正在安装依赖包...")

    requirements = [
        "pyqt6>=6.7.0",
        "pyperclip>=1.8.2",
        "requests>=2.31.0",
        "plyer>=2.1.0",
        "pyinstaller>=6.0.0",
        "pillow>=10.0.0"
    ]

    try:
        # 升级pip
        subprocess.run([pip_path, "install", "--upgrade", "pip"],
                       capture_output=True, text=True)

        # 安装依赖
        for package in requirements:
            print(f"  安装 {package}...")
            result = subprocess.run([pip_path, "install", package],
                                    capture_output=True, text=True)
            if result.returncode != 0:
                print(f"  ✗ {package} 安装失败: {result.stderr}")
            else:
                print(f"  ✓ {package} 安装成功")

        return True
    except Exception as e:
        print(f"✗ 依赖安装失败: {str(e)}")
        return False


def create_icon():
    """创建默认图标（如果不存在）"""
    icon_file = "icon.ico"
    if os.path.exists(icon_file):
        print("✓ 图标文件已存在")
        return icon_file

    print("正在创建默认图标...")
    try:
        # 使用PIL创建简单的图标
        from PIL import Image, ImageDraw, ImageFont
        import numpy as np

        # 创建256x256的图像
        img = Image.new('RGBA', (256, 256), (66, 133, 244, 255))
        draw = ImageDraw.Draw(img)

        # 绘制圆形背景
        draw.ellipse([20, 20, 236, 236], fill=(52, 120, 246, 255))

        # 添加IP文字
        try:
            # 尝试使用系统字体
            font = ImageFont.truetype("arial.ttf", 100)
        except:
            # 使用默认字体
            font = ImageFont.load_default()

        # 计算文字位置
        text = "IP"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        position = ((256 - text_width) // 2, (256 - text_height) // 2)

        # 绘制文字
        draw.text(position, text, fill=(255, 255, 255, 255), font=font)

        # 保存为ICO格式
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        img.save(icon_file, format='ICO', sizes=sizes)

        print("✓ 默认图标创建成功")
        return icon_file
    except Exception as e:
        print(f"✗ 图标创建失败: {str(e)}")
        print("  将使用PyInstaller默认图标")
        return None


def create_version_info():
    """创建版本信息文件"""
    version_info = '''# UTF-8
#
# For more details about fixed file info 'ffi' see:
# https://learn.microsoft.com/en-us/windows/win32/menurc/vs-versioninfo-resource
VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=(1, 0, 0, 0),
        prodvers=(1, 0, 0, 0),
        mask=0x3f,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0)
    ),
    kids=[
        StringFileInfo([
            StringTable(
                u'040904B0',
                [StringStruct(u'CompanyName', u'Mingxin'),
                 StringStruct(u'FileDescription', u'剪贴宝'),
                 StringStruct(u'FileVersion', u'1.0.0.0'),
                 StringStruct(u'InternalName', u'IPAnalyzer'),
                 StringStruct(u'LegalCopyright', u'Copyright © 2025 - 2026 IP Analyzer'),
                 StringStruct(u'OriginalFilename', u'IPAnalyzer.exe'),
                 StringStruct(u'ProductName', u'IP Analyzer'),
                 StringStruct(u'ProductVersion', u'1.0.0.0')])
        ]),
        VarFileInfo([VarStruct(u'Translation', [0x409, 1200])])
    ]
)
'''

    with open('version_info.txt', 'w', encoding='utf-8') as f:
        f.write(version_info)

    return 'version_info.txt'


def build_exe(python_path, icon_file, version_file):
    """使用PyInstaller打包EXE"""
    print("正在打包为EXE文件...")

    # 清理旧的构建文件
    for dir_name in ['build', 'dist']:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)

    # 构建PyInstaller命令
    cmd = [
        python_path, '-m', 'PyInstaller',
        '--onefile',  # 打包为单个文件
        '--windowed',  # 窗口程序（不显示控制台）
        '--clean',  # 清理临时文件
        '--noconfirm',  # 覆盖输出目录不确认
        '--name=IPAnalyzer',  # 输出文件名
    ]

    if icon_file and os.path.exists(icon_file):
        cmd.append(f'--icon={icon_file}')

    if version_file and os.path.exists(version_file):
        cmd.append(f'--version-file={version_file}')

    # 添加隐藏导入
    hidden_imports = [
        'plyer.platforms.win.notification',
        'plyer.platforms.win.filechooser',
        'plyer.platforms.win.info',
        'PIL._tkinter_finder'
    ]

    for imp in hidden_imports:
        cmd.append(f'--hidden-import={imp}')

    # 添加数据文件
    cmd.append('--add-data=main.py;.')
    cmd.append('--add-data=config.py;.')

    # 添加UPX压缩（如果可用）
    upx_dir = os.path.join(os.path.dirname(__file__), 'upx')
    if os.path.exists(upx_dir):
        cmd.append(f'--upx-dir={upx_dir}')

    # 主程序文件
    cmd.append('main.py')

    print("执行命令:", ' '.join(cmd))

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

        if result.returncode == 0:
            print("✓ EXE打包成功！")

            # 显示输出信息
            if result.stdout:
                print("输出信息:", result.stdout[:500])

            # 检查生成的EXE文件
            exe_path = os.path.join('dist', 'IPAnalyzer.exe')
            if os.path.exists(exe_path):
                file_size = os.path.getsize(exe_path) / (1024 * 1024)  # MB
                print(f"✓ EXE文件位置: {os.path.abspath(exe_path)}")
                print(f"✓ 文件大小: {file_size:.2f} MB")

                # 复制到当前目录
                shutil.copy(exe_path, 'IPAnalyzer.exe')
                print("✓ 已复制到当前目录: IPAnalyzer.exe")
            else:
                print("✗ EXE文件未找到")
                return False
        else:
            print("✗ EXE打包失败")
            print("错误信息:", result.stderr)
            return False

        return True
    except Exception as e:
        print(f"✗ 打包过程出错: {str(e)}")
        return False


def create_installer():
    """创建安装程序（可选）"""
    print("正在创建安装程序...")

    try:
        # 创建NSIS安装脚本
        nsis_script = '''!define APP_NAME "IP Analyzer"
!define APP_VERSION "1.0.0"
!define APP_PUBLISHER "IP Analyzer Team"
!define APP_URL "https://github.com/yourusername/ip-analyzer"
!define APP_EXE "IPAnalyzer.exe"

Name "${{APP_NAME}}"
OutFile "IPAnalyzer_Setup.exe"
InstallDir "$PROGRAMFILES\\${{APP_NAME}}"
InstallDirRegKey HKCU "Software\\${{APP_NAME}}" "Install_Dir"
RequestExecutionLevel admin

Page directory
Page instfiles

UninstPage uninstConfirm
UninstPage instfiles

Section "主程序"
    SetOutPath "$INSTDIR"
    File "dist\\IPAnalyzer.exe"

    # 创建开始菜单快捷方式
    CreateDirectory "$SMPROGRAMS\\${{APP_NAME}}"
    CreateShortcut "$SMPROGRAMS\\${{APP_NAME}}\\${{APP_NAME}}.lnk" "$INSTDIR\\${{APP_EXE}}"
    CreateShortcut "$DESKTOP\\${{APP_NAME}}.lnk" "$INSTDIR\\${{APP_EXE}}"

    # 写入注册表信息
    WriteRegStr HKCU "Software\\${{APP_NAME}}" "Install_Dir" "$INSTDIR"
    WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${{APP_NAME}}" "DisplayName" "${{APP_NAME}}"
    WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${{APP_NAME}}" "UninstallString" '"$INSTDIR\\uninstall.exe"'
    WriteRegDWORD HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${{APP_NAME}}" "NoModify" 1
    WriteRegDWORD HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${{APP_NAME}}" "NoRepair" 1

    # 创建卸载程序
    WriteUninstaller "$INSTDIR\\uninstall.exe"
SectionEnd

Section "Uninstall"
    DeleteRegKey HKCU "Software\\${{APP_NAME}}"
    DeleteRegKey HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${{APP_NAME}}"

    Delete "$SMPROGRAMS\\${{APP_NAME}}\\*.*"
    RMDir "$SMPROGRAMS\\${{APP_NAME}}"
    Delete "$DESKTOP\\${{APP_NAME}}.lnk"

    Delete "$INSTDIR\\*.*"
    RMDir "$INSTDIR"
SectionEnd
'''

        with open('installer.nsi', 'w', encoding='utf-8') as f:
            f.write(nsis_script)

        print("✓ 安装脚本已创建")
        print("  使用NSIS编译 installer.nsi 创建安装包")

        return True
    except Exception as e:
        print(f"✗ 创建安装程序失败: {str(e)}")
        return False


def cleanup():
    """清理临时文件"""
    print("正在清理临时文件...")

    files_to_remove = [
        'version_info.txt',
        'installer.nsi',
        'IPAnalyzer.spec'
    ]

    for file in files_to_remove:
        if os.path.exists(file):
            os.remove(file)
            print(f"  已删除: {file}")

    # 清理__pycache__
    for root, dirs, files in os.walk('.'):
        if '__pycache__' in dirs:
            cache_dir = os.path.join(root, '__pycache__')
            shutil.rmtree(cache_dir)
            print(f"  已删除: {cache_dir}")

    print("✓ 清理完成")


def check_prerequisites():
    """检查系统环境"""
    print("检查系统环境...")

    # 检查Python版本
    python_version = sys.version_info
    print(f"  Python版本: {python_version.major}.{python_version.minor}.{python_version.micro}")

    if python_version.major < 3 or (python_version.major == 3 and python_version.minor < 8):
        print("✗ 需要Python 3.8或更高版本")
        return False

    # 检查操作系统
    if sys.platform != "win32":
        print("✗ 此打包脚本仅支持Windows系统")
        return False

    print("✓ 系统环境检查通过")
    return True


def main():
    """主函数"""
    print("=" * 50)
    print("      IP Analyzer 打包工具")
    print("=" * 50)

    # 检查环境
    if not check_prerequisites():
        return

    # 设置虚拟环境
    env_paths = setup_virtual_env()
    if not env_paths:
        return

    python_path, pip_path = env_paths

    # 安装依赖
    if not install_dependencies(pip_path):
        return

    # 创建图标
    icon_file = create_icon()

    # 创建版本信息
    version_file = create_version_info()

    # 打包EXE
    if not build_exe(python_path, icon_file, version_file):
        return

    # 可选：创建安装程序
    print("\n是否创建安装程序？ (y/N): ", end="")
    choice = input().strip().lower()
    if choice == 'y':
        create_installer()

    # 清理
    cleanup()

    print("\n" + "=" * 50)
    print("打包完成！")
    print("=" * 50)
    print("\n使用方法:")
    print("1. 直接运行: dist\\IPAnalyzer.exe")
    print("2. 首次运行会自动设置开机启动")
    print("3. 程序会在系统托盘运行")
    print("4. 复制IP地址会自动显示通知")
    print("\n注意事项:")
    print("- 确保网络连接正常")
    print("- Windows Defender可能会误报，请添加到信任列表")
    print("- 首次启动可能需要几秒钟")
    print("\n按Enter键退出...")
    input()


if __name__ == "__main__":
    main()