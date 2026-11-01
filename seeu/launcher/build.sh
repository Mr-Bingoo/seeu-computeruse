#!/bin/sh
# 生成 SeeU.app(SeeU 小程序)。用法:sh seeu/launcher/build.sh
# ⚠️ 本机自签名,重新生成后系统可能要你再授权一次 SeeU。
set -e
cd "$(dirname "$0")"
A=SeeU.app/Contents
rm -rf SeeU.app && mkdir -p $A/MacOS $A/Resources
# 图标:AppIcon.svg 是原图(11-01 用户在 seeu/参考/小程序图标/预览3.html 定),AppIcon.icns 由它生成
cp AppIcon.icns $A/Resources/
clang -O2 -arch arm64 -arch x86_64 -o $A/MacOS/SeeU seeu_launcher.c
cat > $A/Info.plist <<P
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>SeeU</string>
<key>CFBundleIdentifier</key><string>io.github.seeu.launcher</string>
<key>CFBundleName</key><string>SeeU</string>
<key>CFBundleDisplayName</key><string>SeeU</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>1.0</string>
<key>LSUIElement</key><true/>
<key>LSMinimumSystemVersion</key><string>12.0</string>
</dict></plist>
P
codesign -s - -f --identifier io.github.seeu.launcher SeeU.app
echo "好了:$(pwd)/SeeU.app"
