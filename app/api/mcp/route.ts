import { createMcpHandler } from "mcp-handler";
import { tool } from "@langchain/core/tools";
import { z } from "zod";
import Replicate from "replicate";
import { readFile } from "node:fs/promises";

const replicate = new Replicate();

const OMNIPARSER_MODEL =
  "microsoft/omniparser-v2:49cf3d41b8d3aca1360514e83be4c97131ce8f0d99abfc365526d8384caa88df" as const;

const omniparserInputSchema = {
  image: z
    .string()
    .min(1)
    .describe(
      "The image to parse. Accepts: an http(s) URL, a base64 data URI (data:image/...;base64,...), or an absolute path to a file on the server's disk.",
    ),
};

async function resolveImage(image: string): Promise<string | Buffer> {
  if (
    image.startsWith("http://") ||
    image.startsWith("https://") ||
    image.startsWith("data:")
  ) {
    return image;
  }
  return await readFile(image);
}

const omniparserTool = tool(
  async ({ image }: { image: string }) => {
    const resolved = await resolveImage(image);
    const output = await replicate.run(OMNIPARSER_MODEL, {
      input: { image: resolved },
    });
    return typeof output === "string" ? output : JSON.stringify(output);
  },
  {
    name: "run_omniparser",
    description:
      "Run microsoft/omniparser-v2 on Replicate to detect and label interactive UI elements in a screenshot. Accepts an http(s) URL, a base64 data URI, or a server-local file path.",
    schema: z.object(omniparserInputSchema),
  },
);

const handler = createMcpHandler(
  (server) => {
    server.registerTool(
      omniparserTool.name,
      {
        description: omniparserTool.description ?? "",
        inputSchema: omniparserInputSchema,
      },
      async (args) => {
        const result = await omniparserTool.invoke(args);
        return {
          content: [
            {
              type: "text",
              text: typeof result === "string" ? result : JSON.stringify(result),
            },
          ],
        };
      },
    );
  },
  {
    serverInfo: { name: "kira-mcp", version: "0.1.0" },
  },
  {
    basePath: "/api",
    disableSse: true,
  },
);

export { handler as GET, handler as POST, handler as DELETE };
