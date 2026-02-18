# 如何上传代码到 GitHub (修复版)

## 1. 确认位置

你当前看到的这个文件夹就是 Git 仓库根目录。
路径: `/Users/hemin/.../PiBot_V3_Source`

## 2. 打开终端

在 Mac 上打开终端，执行：

cd "/Users/hemin/Library/CloudStorage/SynologyDrive-01/Obsidian/何慜的笔记/03\_技术探索/硬件设备/PiBot_V3_Source"

## 3. 修复关联 (核心步骤)

因为之前可能添加了错误的地址，请按顺序执行：

# 删除旧的

git remote remove origin

# 添加新的 (您的专属地址)

git remote add origin https://github.com/justonehe/PiBot.git

## 4. 推送

git branch -M main
git push -u origin main
