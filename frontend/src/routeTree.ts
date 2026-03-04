import { rootRoute } from "./routes/__root";
import { indexRoute } from "./routes/index";
import { historyRoute } from "./routes/history";

export const routeTree = rootRoute.addChildren([indexRoute, historyRoute]);
