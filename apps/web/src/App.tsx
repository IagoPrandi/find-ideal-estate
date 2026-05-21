import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Analytics } from "@vercel/analytics/react";
import { AuthProvider } from "./features/auth/AuthContext";
import { ScrapingAdminPage } from "./features/admin/ScrapingAdminPage";
import { FindIdealApp } from "./features/app/FindIdealApp";

const queryClient = new QueryClient();

export default function App() {
  const [client] = useState(() => queryClient);
  const [hashRoute, setHashRoute] = useState(() => window.location.hash);

  useEffect(() => {
    const onHashChange = () => setHashRoute(window.location.hash);
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const isAdminRoute = hashRoute === "#/admin" || hashRoute === "#/admin/scraping";

  return (
    <QueryClientProvider client={client}>
      <AuthProvider>
        {isAdminRoute ? <ScrapingAdminPage /> : <FindIdealApp />}
        <Analytics />
      </AuthProvider>
    </QueryClientProvider>
  );
}
