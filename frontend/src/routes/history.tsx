import { createRoute } from "@tanstack/react-router";
import { rootRoute } from "./__root";
import { Clock, Trash2 } from "lucide-react";

function HistoryPage() {
  return (
    <div className="flex flex-col h-full bg-slate-50/30">
      <div className="px-8 py-10 max-w-4xl mx-auto w-full">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-slate-800 tracking-tight">历史记录</h1>
            <p className="text-sm text-slate-500 mt-1">查看之前的对话记录</p>
          </div>
          <button className="flex items-center gap-2 px-4 py-2 text-sm text-rose-600 bg-white border border-rose-100 hover:bg-rose-50 rounded-xl transition-colors font-medium shadow-sm">
            <Trash2 className="w-4 h-4" />
            清空记录
          </button>
        </div>

        <div className="flex flex-col items-center justify-center py-24 bg-white rounded-3xl border border-slate-200 border-dashed">
          <div className="w-16 h-16 bg-slate-50 border border-slate-100 text-slate-400 rounded-2xl flex items-center justify-center mb-5 rotate-3">
            <Clock className="w-8 h-8" />
          </div>
          <h3 className="text-lg font-semibold text-slate-700 mb-2">暂无历史记录</h3>
          <p className="text-slate-500 text-sm max-w-sm text-center leading-relaxed">
            历史功能正在开发中。目前的对话数据仅保存在浏览器内存，刷新页面后将被清除。
          </p>
        </div>
      </div>
    </div>
  );
}

export const historyRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/history",
  component: HistoryPage,
});