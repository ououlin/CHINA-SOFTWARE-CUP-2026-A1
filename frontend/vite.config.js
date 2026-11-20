import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import viteCompression from 'vite-plugin-compression'

// 开发期把 /api 代理到后端，规避跨域；生产由 Nginx 同源反代。
export default defineConfig(({ mode }) => ({
  plugins: [
    vue(),
    // Element Plus 按需引入：模板里的 el-* 组件与其样式由解析器自动引入，
    // ElMessage / ElMessageBox 等命令式 API 由 AutoImport 注入，避免全量注册。
    AutoImport({
      resolvers: [ElementPlusResolver()],
      dts: false,
    }),
    Components({
      resolvers: [ElementPlusResolver()],
      dts: false,
    }),
    // 生产 gzip 预压缩：生成 .gz，配合 Nginx `gzip_static on` 直接发压缩件，
    // 省 CPU、国产化服务器/小带宽下加载提速数倍。
    viteCompression({ algorithm: 'gzip', ext: '.gz', threshold: 10240, deleteOriginFile: false }),
  ],
  // 生产移除 console/debugger：减小体积且避免泄露调试信息（开发期保留）
  esbuild: mode === 'production' ? { drop: ['console', 'debugger'] } : {},
  build: {
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        // 框架运行时与图表库单独成块，便于浏览器长缓存；其余按路由自动拆包。
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('/echarts/') || id.includes('/zrender/')) return 'echarts'
          if (
            id.includes('/node_modules/vue/') ||
            id.includes('/node_modules/@vue/') ||
            id.includes('/vue-router/') ||
            id.includes('/pinia/')
          ) {
            return 'vendor'
          }
        },
      },
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
}))
