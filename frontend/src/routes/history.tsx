import { createRoute } from "@tanstack/react-router";
import { rootRoute } from "./__root";
import { Clock } from "lucide-react";

function HistoryPage() {
  return (
    <div className="max-w-3xl mx-auto p-4">
      <div className="flex flex-col items-center justify-center h-[60vh] text-slate-500 gap-3">
        <Clock className="w-12 h-12 text-blue-200" />
        <p className="text-lg font-medium text-slate-700">历史会话</p>
        <p className="text-sm text-center text-slate-500">
          历史会话功能尚在开发中。
          <br />
          当前对话数据存储在浏览器内存中，刷新后将清除。
        </p>
      </div>
    </div>
  );
}

export const historyRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/history",
  component: HistoryPage,
});
