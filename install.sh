#!/bin/sh
# Install the standalone voicebench executable from the GitHub Releases.
#
#   curl -fsSL https://raw.githubusercontent.com/superintelligenceco/voicebench/main/install.sh | sh
#
# Environment variables:
#   VOICEBENCH_VERSION      Release tag to install, for example v0.2.0. Default: the latest release.
#   VOICEBENCH_INSTALL_DIR  Directory for the executable. Default: $HOME/.local/bin.
set -eu

repo="superintelligenceco/voicebench"
version="${VOICEBENCH_VERSION:-latest}"
install_dir="${VOICEBENCH_INSTALL_DIR:-$HOME/.local/bin}"

err() {
  echo "voicebench install: $*" >&2
  exit 1
}

os=$(uname -s)
arch=$(uname -m)
case "$os" in
  Linux) os=linux ;;
  Darwin) os=macos ;;
  *) err "unsupported operating system: $os. Install the wheel with pip instead." ;;
esac
case "$arch" in
  x86_64 | amd64) arch=x64 ;;
  aarch64 | arm64) arch=arm64 ;;
  *) err "unsupported architecture: $arch. Install the wheel with pip instead." ;;
esac
if [ "$os" = macos ] && [ "$arch" = x64 ]; then
  err "no executable for macOS on Intel. Install the wheel with pip instead."
fi
asset="voicebench-${os}-${arch}"

if [ "$version" = latest ]; then
  base="https://github.com/${repo}/releases/latest/download"
else
  base="https://github.com/${repo}/releases/download/${version}"
fi

if command -v curl > /dev/null 2>&1; then
  fetch() { curl -fsSL -o "$2" "$1"; }
elif command -v wget > /dev/null 2>&1; then
  fetch() { wget -q -O "$2" "$1"; }
else
  err "curl or wget is required"
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT INT TERM

echo "Downloading ${asset} (${version})"
fetch "${base}/${asset}" "${tmp}/${asset}" || err "download failed: ${base}/${asset}"
fetch "${base}/SHA256SUMS" "${tmp}/SHA256SUMS" || err "download failed: ${base}/SHA256SUMS"

expected=$(awk -v f="$asset" '$2 == f || $2 == "*" f { print $1 }' "${tmp}/SHA256SUMS")
[ -n "$expected" ] || err "${asset} is missing from SHA256SUMS"
if command -v sha256sum > /dev/null 2>&1; then
  actual=$(sha256sum "${tmp}/${asset}" | awk '{ print $1 }')
else
  actual=$(shasum -a 256 "${tmp}/${asset}" | awk '{ print $1 }')
fi
[ "$expected" = "$actual" ] || err "checksum mismatch for ${asset}"

mkdir -p "$install_dir"
chmod +x "${tmp}/${asset}"
mv "${tmp}/${asset}" "${install_dir}/voicebench"
if [ "$os" = macos ]; then
  xattr -d com.apple.quarantine "${install_dir}/voicebench" 2> /dev/null || true
fi

echo "Installed $("${install_dir}/voicebench" --version) to ${install_dir}/voicebench"
case ":${PATH}:" in
  *":${install_dir}:"*) ;;
  *) echo "Add ${install_dir} to your PATH to run voicebench from any directory." ;;
esac
