export const reviews = [
  {
    jobId: 'demo-01',
    projectId: '1',
    projectPath: 'java_group/metric-service',
    mrLabel: '!100',
    mrUrl: '#',
    targetBranch: 'main',
    commitShort: 'abc12345',
    status: 'success',
    high: 2,
    medium: 1,
    low: 1,
    commentCount: 4,
    totalTokensFmt: '156K',
    files: [
      {
        path: 'src/main/java/io/binghe/metric/config/MetricConfig.java',
        issues: [
          {
            id: 1,
            level: 'HIGH',
            priority: '高',
            line: 20,
            title: '使用 System.out.println 进行日志记录',
            description: '当前代码使用 System.out.println() 输出日志，未使用 SLF4J 等专业日志框架。这会导致无法按级别控制日志、无法灵活配置输出目标，且高并发下性能较差。',
            suggestion: '将 System.out.println 替换为 SLF4J + Logback。',
            bestPractice: '使用专业日志框架（SLF4J + Logback/Log4j2）记录日志，避免直接输出到控制台。',
            original: 'System.out.println("添加测试日志...");\nSystem.out.println("添加测试日志...");',
            revised: 'private static final Logger log = LoggerFactory.getLogger(MetricConfig.class);\n\nlog.info("添加测试日志...");'
          },
          {
            id: 2,
            level: 'HIGH',
            priority: '中',
            line: 20,
            title: '存在重复日志输出语句',
            description: '同一位置出现两条完全相同的 System.out.println("添加测试日志...")，疑似复制粘贴残留。',
            suggestion: '删除重复语句，保留一条；同时替换为日志框架。',
            bestPractice: '遵循 DRY 原则，避免无意义代码重复。',
            original: 'System.out.println("添加测试日志...");\nSystem.out.println("添加测试日志...");',
            revised: 'log.info("添加测试日志...");'
          }
        ]
      },
      {
        path: 'src/main/java/io/binghe/metric/service/MetricCollector.java',
        issues: [
          {
            id: 3,
            level: 'MEDIUM',
            priority: '中',
            line: 45,
            title: '循环内重复调用 size()',
            description: 'for 循环条件中直接调用 list.size()，每次迭代都会重新计算，集合较大时存在不必要的开销。',
            suggestion: '在循环外缓存 size() 结果，或使用 for-each 遍历。',
            bestPractice: '避免在循环中重复调用不变的方法。',
            original: 'for (int i = 0; i < list.size(); i++) {\n    Metric m = list.get(i);\n    ...\n}',
            revised: 'int size = list.size();\nfor (int i = 0; i < size; i++) {\n    Metric m = list.get(i);\n    ...\n}\n\n// 或更简洁：\nfor (Metric m : list) {\n    ...\n}'
          }
        ]
      },
      {
        path: 'src/main/java/io/binghe/metric/util/DateUtil.java',
        issues: [
          {
            id: 4,
            level: 'LOW',
            priority: '低',
            line: 12,
            title: '魔法值 1000 缺少常量命名',
            description: '代码中直接使用 1000 表示毫秒转换，可读性差。',
            suggestion: '提取为 MILLISECONDS_PER_SECOND 常量。',
            bestPractice: '使用具名常量替代魔法值。',
            original: 'return seconds * 1000;',
            revised: 'private static final int MILLISECONDS_PER_SECOND = 1000;\n\nreturn seconds * MILLISECONDS_PER_SECOND;'
          }
        ]
      }
    ]
  },
  {
    jobId: 'demo-02',
    projectId: '2',
    projectPath: 'go_group/parser',
    mrLabel: '!17',
    mrUrl: '#',
    targetBranch: 'develop',
    commitShort: 'def67890',
    status: 'success',
    high: 1,
    medium: 0,
    low: 2,
    commentCount: 3,
    totalTokensFmt: '89K',
    files: [
      {
        path: 'parser.go',
        issues: [
          {
            id: 1,
            level: 'HIGH',
            priority: '高',
            line: 34,
            title: '忽略 error 返回值',
            description: '调用可能返回 error 的函数后未检查 err，可能导致后续逻辑基于无效数据运行。',
            suggestion: '显式检查 error 并返回或记录。',
            bestPractice: 'Go 中永远不要忽略 error 返回值。',
            original: 'data, _ := parseInput(raw)\nprocess(data)',
            revised: 'data, err := parseInput(raw)\nif err != nil {\n    return nil, fmt.Errorf("parse input: %w", err)\n}\nprocess(data)'
          }
        ]
      }
    ]
  },
  {
    jobId: 'demo-03',
    projectId: '1',
    projectPath: 'java_group/auth-gateway',
    mrLabel: '!42',
    mrUrl: '#',
    targetBranch: 'main',
    commitShort: 'ghi11122',
    status: 'failed',
    high: 0,
    medium: 0,
    low: 0,
    commentCount: 0,
    totalTokensFmt: '—',
    files: []
  }
]

export function getReview(jobId) {
  return reviews.find(r => r.jobId === jobId)
}

export function countIssues(review) {
  let high = 0, medium = 0, low = 0
  if (!review.files) return { high, medium, low }
  review.files.forEach(f => {
    f.issues.forEach(i => {
      if (i.level === 'HIGH') high++
      else if (i.level === 'MEDIUM') medium++
      else low++
    })
  })
  return { high, medium, low }
}
