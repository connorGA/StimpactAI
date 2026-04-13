import { useMutation } from "@tanstack/react-query";

import { requestExample } from "./lib/requestClient";

export default function App() {
  const mutation = useMutation({
    mutationKey: ["requests", "create"],
    mutationFn: async () => {
      await requestExample("/requests");
      return "ok";
    },
    onError: () => {
      // The UI should be free to keep its toast or inline messaging.
    },
  });

  return (
    <main>
      <button onClick={() => mutation.mutate()} type="button">
        Trigger
      </button>
    </main>
  );
}
