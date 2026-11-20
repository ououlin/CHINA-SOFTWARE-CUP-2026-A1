/**
 * ECharts 按需注册入口。
 *
 * 只把项目实际用到的图表类型与组件打进包里，避免整包引入 echarts
 * 把完整发行版（约 1.1 MB）塞进首屏。新增图表类型时在这里登记一次即可。
 *
 * 当前登记：line / bar / pie / graph / sankey / tree
 * 组件：tooltip / legend / grid / title
 */
import * as echarts from 'echarts/core'
import {
  BarChart,
  GraphChart,
  LineChart,
  PieChart,
  SankeyChart,
  TreeChart,
} from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
} from 'echarts/components'
import { LabelLayout } from 'echarts/features'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  LineChart,
  BarChart,
  PieChart,
  GraphChart,
  SankeyChart,
  TreeChart,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  TitleComponent,
  LabelLayout,
  CanvasRenderer,
])

/** 统一导出命名空间，业务侧继续使用 echarts.init / echarts.graphic。 */
export { echarts }

/** 主题切换后需要手动重绘时，统一从这里取实例。 */
export const graphic = echarts.graphic

export default echarts
