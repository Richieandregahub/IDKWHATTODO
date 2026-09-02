#!/bin/bash
# recon — one-liner install
# Run: bash <(curl -sL https://raw.githubusercontent.com/Richieandregahub/IDKWHATTODO/main/install.sh)

set -e

INSTALL_DIR="${1:-/usr/local/bin}"
FILE="recon.py"
URL="https://raw.githubusercontent.com/Richieandregahub/IDKWHATTODO/main/recon.py"

echo "  Installing recon..."
echo "  Downloading from: $URL"

if command -v curl &>/dev/null; then
    curl -sL "$URL" -o "/tmp/$FILE"
elif command -v wget &>/dev/null; then
    wget -q "$URL" -O "/tmp/$FILE"
else
    echo "  ERROR: need curl or wget"
    exit 1
fi

chmod +x "/tmp/$FILE"

if [ -w "$INSTALL_DIR" ]; then
    mv "/tmp/$FILE" "$INSTALL_DIR/recon"
else
    sudo mv "/tmp/$FILE" "$INSTALL_DIR/recon" 2>/dev/null || {
        mkdir -p "$HOME/.local/bin"
        mv "/tmp/$FILE" "$HOME/.local/bin/recon"
        echo "  Put ~/.local/bin in your PATH:  export PATH=\"\$PATH:\$HOME/.local/bin\""
    }
fi

echo "  Done! Run: recon -y --demo ip 8.8.8.8"
