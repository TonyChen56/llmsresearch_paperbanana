# Git Fork 同步工作流

## 初始设置

Fork 原仓库到自己的 GitHub 后，克隆并添加上游 remote：

```bash
git clone git@github.com:你的用户名/PaperBanana.git
cd PaperBanana

# 添加上游 remote
git remote add upstream https://github.com/dwzhu-pku/PaperBanana.git
# 或
git remote add upstream https://github.com/llmsresearch/paperbanana.git
```

此时有两个 remote：
- `origin` → 你的 Fork
- `upstream` → 原作者仓库

## 分支策略

```
main          ← 保持和上游同步，不直接改
  └── dev     ← 你的改造都在这里
```

初始创建 dev 分支：

```bash
git checkout -b dev
git push origin dev
```

## 拉取上游更新

```bash
# 1. 拉取上游最新代码
git fetch upstream

# 2. 先同步 main
git checkout main
git merge upstream/main
git push origin main

# 3. 再把更新合入你的开发分支
git checkout dev
git merge main
git push origin dev
```

## 处理冲突

合并时如果你改过的文件上游也改了，会产生冲突。减少冲突的原则：

- **改造放在独立文件/目录里**（如 `api/`），尽量不改原文件
- **必须改原文件时**，用 wrapper 模式包装而不是直接修改

## 日常开发流程

```bash
# 在 dev 分支上开发
git checkout dev
# ... 改代码 ...
git add . && git commit -m "feat: 导出 API 接口"
git push origin dev

# 定期同步上游（建议每周一次）
git fetch upstream
git checkout main && git merge upstream/main && git push origin main
git checkout dev && git merge main && git push origin dev
```
