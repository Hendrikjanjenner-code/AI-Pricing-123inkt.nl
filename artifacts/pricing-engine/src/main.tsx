import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";
import { installGlobalFetchTimeout } from "@/lib/fetch-timeout";
import { installShopScopedFetch } from "@/lib/shop-scope-fetch";

// Must run before any page/module code issues a fetch() call.
installGlobalFetchTimeout();
installShopScopedFetch();

createRoot(document.getElementById("root")!).render(<App />);
