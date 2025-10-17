#!/bin/bash

# 脚本开始
echo "🚀 自动化脚本启动..."

# 定义变量
VENV_DIR="venv"  # 虚拟环境目录
PYTHON_REQUIREMENTS="requirements.txt"  # 依赖文件
PYTHON_SCRIPT="cvpr_oral.py"  # 要运行的 Python 脚本

# 检查 Python 是否可用
if ! command -v python3 &>/dev/null; then
    echo "❌ 未找到 Python 3，请安装 Python 3 后重试。"
    exit 1
fi

# 创建虚拟环境
echo "📦 检查虚拟环境..."
if [ ! -d "$VENV_DIR" ]; then
    echo "🌱 创建虚拟环境..."
    python3 -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo "❌ 创建虚拟环境失败，请检查 Python 安装。"
        exit 1
    fi
else
    echo "✅ 虚拟环境已存在：$VENV_DIR"
fi

# 激活虚拟环境
echo "🔑 激活虚拟环境..."
source "$VENV_DIR/bin/activate"
if [ $? -ne 0 ]; then
    echo "❌ 激活虚拟环境失败。"
    exit 1
fi

# 确保 pip 已更新
echo "🔄 更新 pip..."
pip install --upgrade pip

# 安装依赖
if [ -f "$PYTHON_REQUIREMENTS" ]; then
    echo "📚 安装依赖 (requirements.txt)..."
    pip install -r "$PYTHON_REQUIREMENTS"
    if [ $? -ne 0 ]; then
        echo "❌ 安装依赖失败，请检查 requirements.txt 文件。"
        deactivate
        exit 1
    fi
else
    echo "⚠️ 未找到 requirements.txt，跳过依赖安装。"
fi

# 检查 Python 脚本是否存在
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "❌ 未找到 Python 脚本：$PYTHON_SCRIPT，请检查路径。"
    deactivate
    exit 1
fi

# 运行 Python 脚本
echo "🐍 运行 Python 脚本：$PYTHON_SCRIPT"
python "$PYTHON_SCRIPT" "$@"
if [ $? -ne 0 ]; then
    echo "❌ Python 脚本运行失败。"
    deactivate
    exit 1
fi

# 脚本运行成功
echo "✅ 脚本运行完成！"

# 退出虚拟环境
echo "🔒 退出虚拟环境..."
deactivate