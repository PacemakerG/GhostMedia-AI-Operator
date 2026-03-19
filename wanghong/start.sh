#!/bin/bash
# X 平台内容抓取启动脚本

echo "=================================="
echo "  X 平台内容抓取工具"
echo "=================================="

# 检查 Python
echo "[*] 检查 Python 环境..."
if ! command -v python3 &> /dev/null; then
    echo "[✗] 未找到 Python3，请先安装"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "[✓] Python 版本: $PYTHON_VERSION"

# 检查虚拟环境
echo "[*] 检查虚拟环境..."
VENV_DIR="venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "[*] 创建虚拟环境..."
    python3 -m venv $VENV_DIR
fi

# 激活虚拟环境
echo "[*] 激活虚拟环境..."
source $VENV_DIR/bin/activate

# 安装依赖
echo "[*] 检查依赖..."
pip install -q -r requirements.txt

# 检查配置文件
echo "[*] 检查配置文件..."
CONFIG_FILE="config/config.yaml"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "[✗] 配置文件不存在: $CONFIG_FILE"
    echo "[*] 请复制 config.example.yaml 并进行配置"
    exit 1
fi

# 创建必要的目录
echo "[*] 创建数据目录..."
mkdir -p data/{raw,processed}
mkdir -p data/raw/media/{images,videos}
mkdir -p logs

# 显示使用说明
echo ""
echo "=================================="
echo "  启动成功！"
echo "=================================="
echo ""
echo "使用示例:"
echo "  1. 抓取猫神的20条推文并改写:"
echo "     python src/main.py -u Maoshen9527 -l 20"
echo ""
echo "  2. 使用专业风格改写:"
echo "     python src/main.py -u Maoshen9527 -s professional"
echo ""
echo "  3. 只抓取不下载媒体:"
echo "     python src/main.py -u Maoshen9527 --no-download"
echo ""
echo "配置文件: $CONFIG_FILE"
echo "数据目录: data/"
echo "日志文件: logs/"
echo ""
echo "=================================="

# 保持虚拟环境激活
exec $SHELL
