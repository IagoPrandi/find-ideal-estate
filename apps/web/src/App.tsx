import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Analytics } from "@vercel/analytics/react";
import { SpeedInsights } from "@vercel/speed-insights/react";
import { AuthProvider } from "./features/auth/AuthContext";
import { ScrapingAdminPage } from "./features/admin/ScrapingAdminPage";
import { FindIdealApp } from "./features/app/FindIdealApp";
import { SharedJourneyPage } from "./features/share/SharedJourneyPage";
import { SharedZonePage } from "./features/share/SharedZonePage";

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
  const sharedJourneyPrefix = "#/jornada/compartilhada/";
  const sharedJourneyToken = hashRoute.startsWith(sharedJourneyPrefix)
    ? decodeURIComponent(hashRoute.slice(sharedJourneyPrefix.length))
    : null;
  const sharedZonePrefix = "#/zona/compartilhada/";
  const sharedZoneToken = hashRoute.startsWith(sharedZonePrefix)
    ? decodeURIComponent(hashRoute.slice(sharedZonePrefix.length))
    : null;

  return (
    <QueryClientProvider client={client}>
      <AuthProvider>
        {sharedZoneToken ? <SharedZonePage token={sharedZoneToken} /> : sharedJourneyToken ? <SharedJourneyPage token={sharedJourneyToken} /> : isAdminRoute ? <ScrapingAdminPage /> : <FindIdealApp />}
        <Analytics />
        <SpeedInsights />
      </AuthProvider>
    </QueryClientProvider>
  );
}
