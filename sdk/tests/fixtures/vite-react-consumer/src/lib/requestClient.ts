import { captureHandledError } from "../stimpact";

export async function requestExample(endpoint: string): Promise<Response> {
  const method = "POST";
  try {
    const response = await fetch(endpoint, { method });
    if (!response.ok) {
      const error = new Error(`${response.status}: ${response.statusText}`);
      await captureHandledError({
        error,
        request: { method, url: endpoint },
        response: { status_code: response.status },
      });
      throw error;
    }
    return response;
  } catch (error) {
    await captureHandledError({
      error,
      request: { method, url: endpoint },
    });
    throw error;
  }
}
