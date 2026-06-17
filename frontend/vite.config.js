import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import viteCompression from 'vite-plugin-compression'

// 开发期把 /api 代理到后端，规避跨域；生产由 Nginx 同源反代。
export default defineConfig(({ mode }) => ({
  plugins: [
    vue(),
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
        // 拆分大体积第三方库为独立 chunk，利于浏览器缓存与首屏并行加载
        manualChunks: {
          echarts: ['echarts'],
          vendor: ['vue', 'vue-router', 'pinia', 'element-plus'],
          scan: ['qrcode', 'html5-qrcode'],
          markdown: ['marked', 'dompurify'],
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
