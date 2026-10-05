/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        // 拉丁字用 Inter；泰文用有圈圈的傳統字形（Looped），初學者比較好辨認；中文交給系統字型
        sans: ['Inter', '"Noto Sans Thai Looped"', 'Thonburi', '"PingFang TC"', '"Noto Sans TC"', '"Microsoft JhengHei"', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
