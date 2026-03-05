## 提示词规范

1. 提示词中的用户及AI助手的对话历史需要遵循以下格式
- [{"role": "user", "content": "用户输入"}, {"role": "assistant", "content": "AI助手输出"}, {"role":"sytem", "content": "系统提示"}]
- 尽量保持对话内容在前，system在后更改AI的角色，这样能保证命中前方的缓存（前面对话保持一致能命中缓存）而且能动态更改角色