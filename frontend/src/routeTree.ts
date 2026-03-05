import { rootRoute } from "./routes/__root";
import { indexRoute } from "./routes/index";
import { historyRoute } from "./routes/history";
import { conversationRoute } from "./routes/chat.$conversationId";

export const routeTree = rootRoute.addChildren([
  indexRoute,
  historyRoute,
  conversationRoute,
]);
