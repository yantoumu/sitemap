# Prisma 用户表配置

这个目录包含了用户管理系统的 Prisma 数据库配置。

## 📁 文件结构

```
prisma/
├── schema.prisma    # Prisma 数据库模式定义
├── .env.example     # 数据库连接配置示例
└── README.md        # 使用说明（本文件）
```

## 🗄️ 数据表设计

### User 用户表
- **基础信息**: id, username, email, password
- **个人信息**: firstName, lastName, avatar, phone
- **状态管理**: status (ACTIVE/INACTIVE/SUSPENDED/BANNED)
- **角色权限**: role (ADMIN/USER/PREMIUM/DEVELOPER)
- **配置存储**: apiConfig, settings (JSON格式)
- **统计数据**: loginCount, keywordCount, sitemapCount
- **时间戳**: createdAt, updatedAt, lastLoginAt, deletedAt

### UserSession 会话表
- 用户登录会话管理
- Token 验证和过期控制

### UserLog 操作日志表
- 用户操作记录
- IP地址和用户代理追踪

### Student 学生表
- **基础信息**: id, studentId, name, email, phone
- **学籍信息**: grade, major, class, department
- **个人信息**: gender, birthDate, idCard, address
- **状态管理**: status (ACTIVE/SUSPENDED/GRADUATED/DROPPED/TRANSFERRED)
- **学业信息**: enrollDate, graduateDate, gpa, totalCredits
- **时间戳**: createdAt, updatedAt, deletedAt

### Course 课程表
- **课程信息**: courseCode, courseName, credits, hours
- **教学信息**: department, teacher, semester
- **课程描述**: description, prerequisite

### StudentCourse 学生课程关系表
- **关联信息**: studentId, courseId
- **成绩信息**: score, grade, status
- **时间信息**: enrollDate, examDate

## 🚀 使用步骤

### 1. 安装 Prisma
```bash
npm install prisma @prisma/client
# 或
yarn add prisma @prisma/client
```

### 2. 配置数据库连接
```bash
# 复制环境变量模板
cp prisma/.env.example prisma/.env

# 编辑 .env 文件，填入实际的数据库连接信息
# DATABASE_URL="postgresql://username:password@localhost:5432/database"
```

### 3. 生成 Prisma Client
```bash
npx prisma generate
```

### 4. 创建数据库迁移
```bash
# 创建并应用迁移
npx prisma migrate dev --name init

# 或者直接推送到数据库（开发环境）
npx prisma db push
```

### 5. 查看数据库
```bash
# 启动 Prisma Studio
npx prisma studio
```

## 💡 使用示例

### 创建用户
```javascript
const user = await prisma.user.create({
  data: {
    username: 'john_doe',
    email: 'john@example.com',
    password: 'hashed_password',
    firstName: 'John',
    lastName: 'Doe',
    role: 'USER',
    status: 'ACTIVE'
  }
})
```

### 查询用户
```javascript
const user = await prisma.user.findUnique({
  where: { email: 'john@example.com' },
  include: {
    sessions: true,
    logs: true
  }
})
```

### 更新用户统计
```javascript
await prisma.user.update({
  where: { id: userId },
  data: {
    keywordCount: { increment: 1 },
    lastLoginAt: new Date()
  }
})
```

### 创建学生
```javascript
const student = await prisma.student.create({
  data: {
    studentId: '2024001',
    name: '张三',
    email: 'zhangsan@university.edu',
    grade: '2024',
    major: '计算机科学与技术',
    class: '计科1班',
    department: '计算机学院',
    gender: 'MALE',
    status: 'ACTIVE',
    enrollDate: new Date('2024-09-01')
  }
})
```

### 创建课程和选课
```javascript
// 创建课程
const course = await prisma.course.create({
  data: {
    courseCode: 'CS101',
    courseName: '计算机程序设计基础',
    credits: 3,
    hours: 48,
    department: '计算机学院',
    teacher: '李教授',
    semester: '2024-1'
  }
})

// 学生选课
const enrollment = await prisma.studentCourse.create({
  data: {
    studentId: student.id,
    courseId: course.id,
    status: 'ENROLLED'
  }
})
```

### 查询学生成绩
```javascript
const studentWithGrades = await prisma.student.findUnique({
  where: { studentId: '2024001' },
  include: {
    courses: {
      include: {
        course: true
      }
    }
  }
})
```

## 🔧 自定义配置

根据项目需求，您可以：
- 修改字段类型和约束
- 添加新的表和关系
- 调整索引和性能优化
- 扩展枚举类型

## 📚 相关文档

- [Prisma 官方文档](https://www.prisma.io/docs)
- [PostgreSQL 数据类型](https://www.postgresql.org/docs/current/datatype.html)
- [Prisma Schema 参考](https://www.prisma.io/docs/reference/api-reference/prisma-schema-reference)
