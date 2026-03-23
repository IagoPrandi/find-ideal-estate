import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { FindIdealApp } from "./features/app/FindIdealApp";

const queryClient = new QueryClient();

export default function App() {
  const [client] = useState(() => queryClient);
  return (
    <QueryClientProvider client={client}>
      <FindIdealApp />
    </QueryClientProvider>
  );
}
