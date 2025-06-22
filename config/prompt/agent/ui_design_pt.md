# Design a {{设计风格}} mobile UI screen ({{平台风格}}) for an app titled "{{应用名称}}". The layout should follow the structured sections below.

{{#各区域定义开始}}
## 1. {{顶部区域名称}} (Top)
- **Style**: {{顶部区域样式描述}}

---

## 2. {{标题区域名称}} Section
- **{{主标题元素}}**: `{{标题内容}}`
- **Font**: {{字体样式}}
- **Color**: {{主色系}} text

---

## 3. {{特色内容区域名称}} ({{滚动方向}} Scrollable)
- **Style**: {{卡片样式描述}}
- **Cards**:
  {{#循环卡片开始}}
  - **Card {{序号}}**
    - Title: **{{课程标题}}**
    - Subtitle: *{{时间信息}}*
    - Visual: {{视觉元素描述}}
  {{/循环卡片结束}}

---

## 4. {{主导航区域名称}}
- **Tabs**:
  {{#循环标签开始}}
  - **{{标签名称}}** ({{状态}}, {{激活样式描述}})
  {{/循环标签结束}}

---

## 5. {{筛选区域名称}}
- **Filters ({{控件类型}})**:
  {{#循环筛选条件开始}}
  - **{{筛选条件名称}}** ({{筛选类型}})
  {{/循环筛选条件结束}}

---

## 6. {{内容列表区域名称}}
- **Layout**: {{布局方式}} of repeatable items:
  - **{{位置1}}**: {{元素1描述}}
  - **{{位置2}}**:
    - {{子元素1}}
    - {{子元素2}}
  - **{{位置3}}**: {{元素3描述}}
  - **{{位置4}}**: {{统计信息}} + {{趋势指示}}

---

## 7. {{底部导航区域名称}}
- **Tabs**:
  {{#循环底部标签开始}}
  - **{{标签名称}}** ({{状态}}, {{高亮样式}})
  {{/循环底部标签结束}}
- **Style**:
  - {{样式细节描述}}
{{/各区域定义结束}}


## 参数说明手册

| 参数类别 | 参数名称 | 类型 | 选项示例 | 必选 | 默认值 |
|---------|---------|------|---------|------|-------|
| 全局设置 | 设计风格 | 枚举 | clean/modern/minimalist/retro | 是 | modern |
| 全局设置 | 平台风格 | 枚举 | iOS/Android/Cross-platform | 是 | iOS |
| 全局设置 | 应用名称 | 文本 | - | 是 | - |
| 区域设置 | 顶部区域名称 | 文本 | Status Bar/Header Bar | 否 | Status Bar |
| 视觉元素 | 卡片样式描述 | 文本 | rounded corners with shadow/flat design | 否 | rounded corners with soft shadow |
| 内容配置 | 课程标题 | 文本 | - | 条件 | - |
| 交互元素 | 滚动方向 | 枚举 | Horizontal/Vertical/Grid | 否 | Horizontal |

## 变体示例集

### 示例1：电商应用
```markdown
# Design a minimalist mobile UI screen (Android style) for an app titled "ShopEasy - Daily Deals"...

## 3. Featured Products Carousel (Horizontally Scrollable)
- **Style**: Flat cards with border
- **Cards**:
  - **Card 1**
    - Title: **Wireless Earbuds Pro**
    - Subtitle: *Limited-time offer*
    - Visual: Product image
```

### 示例2：新闻阅读器
```markdown
# Design a clean mobile UI screen (iOS style) for an app titled "NewsSphere - Top Stories"...

## 6. Trending Articles List
- **Layout**: Vertical stack of repeatable items:
  - **Left**: Publisher logo
  - **Center**:
    - Article Title
    - Reading time
  - **Center**:
    - Article Title
  - **Center**:
  - **Center**:
    - Article Title
  - **Center**:
  - **Center**:
  - **Center**:
  - **Center**:
  - **Center**:
    - Article Title
    - Reading time
  - **Right**: Bookmark Icon
```