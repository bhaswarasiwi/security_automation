#!/bin/bash
# scripts/install_tools.sh
# Install subfinder, nuclei, httpx di environment Render (Linux amd64)
# Dipanggil otomatis saat build di Render

set -e

TOOLS_DIR="/opt/render/project/tools"
mkdir -p "$TOOLS_DIR"
export PATH="$PATH:$TOOLS_DIR"

echo "==> Mengecek Go tools..."

install_go_tool() {
    local name=$1
    local url=$2

    if command -v "$name" &>/dev/null; then
        echo "  $name sudah ada, skip."
        return
    fi

    echo "  Install $name..."
    curl -sL "$url" -o "/tmp/${name}.tar.gz"
    tar -xzf "/tmp/${name}.tar.gz" -C "$TOOLS_DIR" --wildcards "*/${name}" 2>/dev/null || \
    tar -xzf "/tmp/${name}.tar.gz" -C "$TOOLS_DIR" 2>/dev/null || true

    # cari binary dan pindahkan
    find "$TOOLS_DIR" -name "$name" -type f -exec chmod +x {} \; -exec mv {} "$TOOLS_DIR/$name" \; 2>/dev/null || true
    echo "  $name installed."
}

# Versi terbaru (update secara berkala)
SUBFINDER_VER="v2.6.6"
NUCLEI_VER="v3.3.9"
HTTPX_VER="v1.6.8"

install_go_tool "subfinder" \
  "https://github.com/projectdiscovery/subfinder/releases/download/${SUBFINDER_VER}/subfinder_${SUBFINDER_VER#v}_linux_amd64.zip"

install_go_tool "nuclei" \
  "https://github.com/projectdiscovery/nuclei/releases/download/${NUCLEI_VER}/nuclei_${NUCLEI_VER#v}_linux_amd64.zip"

install_go_tool "httpx" \
  "https://github.com/projectdiscovery/httpx/releases/download/${HTTPX_VER}/httpx_${HTTPX_VER#v}_linux_amd64.zip"

echo "==> Tools selesai diinstall."
echo "PATH tools: $TOOLS_DIR"
ls -la "$TOOLS_DIR/" 2>/dev/null || echo "(kosong)"
