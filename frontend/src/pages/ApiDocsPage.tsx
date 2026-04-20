import {
  Accordion,
  Badge,
  Code,
  Group,
  Stack,
  Table,
  Text,
  Title,
  Divider,
  Alert,
} from "@mantine/core";
import { IconInfoCircle } from "@tabler/icons-react";

type Method = "GET" | "POST" | "PUT" | "DELETE";

const METHOD_COLORS: Record<Method, string> = {
  GET: "green",
  POST: "blue",
  PUT: "yellow",
  DELETE: "red",
};

function MethodBadge({ method }: { method: Method }) {
  return (
    <Badge color={METHOD_COLORS[method]} variant="filled" size="sm" radius="sm">
      {method}
    </Badge>
  );
}

interface Param {
  name: string;
  type: string;
  required: boolean;
  description: string;
}

interface Endpoint {
  method: Method;
  path: string;
  description: string;
  params?: Param[];
  curl?: string;
}

interface Section {
  label: string;
  value: string;
  endpoints: Endpoint[];
}

const BASE = "http://localhost:8181";

const sections: Section[] = [
  {
    label: "Health",
    value: "health",
    endpoints: [
      {
        method: "GET",
        path: "/health",
        description: "Service liveness check. Returns database connectivity status.",
        curl: `curl ${BASE}/health`,
      },
      {
        method: "GET",
        path: "/api/version",
        description: "Returns the current API version string.",
        curl: `curl ${BASE}/api/version`,
      },
    ],
  },
  {
    label: "Coffees",
    value: "coffees",
    endpoints: [
      {
        method: "GET",
        path: "/api/coffees",
        description: "List all coffees sorted by roast date descending.",
        curl: `curl ${BASE}/api/coffees | jq '.[] | {id, name, roaster}'`,
      },
      {
        method: "GET",
        path: "/api/coffees/:id",
        description: "Get a single coffee by ID.",
        curl: `curl ${BASE}/api/coffees/1`,
      },
      {
        method: "POST",
        path: "/api/coffees",
        description: "Create a new coffee.",
        params: [
          { name: "name", type: "string", required: true, description: "Coffee name" },
          { name: "roaster", type: "string", required: true, description: "Roaster name" },
          { name: "roast_date", type: "date (ISO)", required: false, description: "e.g. 2026-03-01" },
          { name: "origin_country", type: "string", required: false, description: "Country of origin" },
          { name: "roast_level", type: "enum", required: false, description: "light | medium | dark" },
          { name: "variety", type: "string", required: false, description: "Bean variety" },
          { name: "process", type: "string", required: false, description: "Processing method" },
        ],
        curl: `curl -X POST ${BASE}/api/coffees \\\n  -H "Content-Type: application/json" \\\n  -d '{"name":"Honduras","roaster":"Onyx","roast_date":"2026-03-15"}'`,
      },
      {
        method: "PUT",
        path: "/api/coffees/:id",
        description: "Update a coffee. All fields optional.",
        curl: `curl -X PUT ${BASE}/api/coffees/1 \\\n  -H "Content-Type: application/json" \\\n  -d '{"roast_date":"2026-04-01"}'`,
      },
      {
        method: "DELETE",
        path: "/api/coffees/:id",
        description: "Delete a coffee. Returns 409 if shots reference it.",
        curl: `curl -X DELETE ${BASE}/api/coffees/1`,
      },
      {
        method: "POST",
        path: "/api/coffees/:id/image",
        description: "Upload a label photo (multipart/form-data, field: file). Replaces existing image.",
        curl: `curl -X POST ${BASE}/api/coffees/1/image \\\n  -F "file=@label.jpg"`,
      },
      {
        method: "DELETE",
        path: "/api/coffees/:id/image",
        description: "Remove the label photo for a coffee.",
        curl: `curl -X DELETE ${BASE}/api/coffees/1/image`,
      },
    ],
  },
  {
    label: "Shots",
    value: "shots",
    endpoints: [
      {
        method: "GET",
        path: "/api/shots",
        description: "List shots with optional filters, ordered by date descending.",
        params: [
          { name: "maker", type: "string", required: false, description: "Filter by maker name" },
          { name: "coffee_id", type: "integer", required: false, description: "Filter by coffee" },
          { name: "date_from", type: "date (ISO)", required: false, description: "Inclusive start date" },
          { name: "date_to", type: "date (ISO)", required: false, description: "Inclusive end date" },
          { name: "limit", type: "integer", required: false, description: "Max results to return" },
          { name: "offset", type: "integer", required: false, description: "Rows to skip (default 0)" },
        ],
        curl: `curl "${BASE}/api/shots?coffee_id=1&limit=10"`,
      },
      {
        method: "GET",
        path: "/api/shots/:id",
        description: "Get a single shot by ID. Includes denormalized labels (coffee_name, grinder_label, etc.).",
        curl: `curl ${BASE}/api/shots/42`,
      },
      {
        method: "POST",
        path: "/api/shots",
        description: "Create a new shot record.",
        params: [
          { name: "date", type: "date (ISO)", required: true, description: "Shot date" },
          { name: "maker", type: "string", required: true, description: "Who pulled the shot" },
          { name: "coffee_id", type: "integer", required: false, description: "Coffee bag ID" },
          { name: "dose_weight", type: "float", required: false, description: "Dose in grams" },
          { name: "extraction_time", type: "float", required: false, description: "Target extraction time (seconds)" },
          { name: "extraction_delta", type: "float", required: false, description: "Actual deviation from target (default 0)" },
          { name: "final_weight", type: "float", required: false, description: "Yield in grams" },
          { name: "grind_setting", type: "string", required: false, description: "Grinder setting value" },
          { name: "grinder_id", type: "integer", required: false, description: "Grinder ID" },
          { name: "device_id", type: "integer", required: false, description: "Brewing device ID" },
          { name: "scale_id", type: "integer", required: false, description: "Scale ID" },
          { name: "drink_type", type: "enum", required: false, description: "americano | latte | cappuccino | drip | other" },
          { name: "grinder_temp_before", type: "float", required: false, description: "Grinder temp before (°C)" },
          { name: "grinder_temp_after", type: "float", required: false, description: "Grinder temp after (°C)" },
          { name: "pre_infusion_time", type: "string", required: false, description: "Pre-infusion duration" },
          { name: "wedge", type: "boolean", required: false, description: "Wedge used (default false)" },
          { name: "shaker", type: "boolean", required: false, description: "Shaker used (default false)" },
          { name: "wdt", type: "boolean", required: false, description: "WDT used (default false)" },
          { name: "flow_taper", type: "boolean", required: false, description: "Flow taper used (default false)" },
          { name: "notes", type: "string", required: false, description: "Free-text notes" },
        ],
        curl: `curl -X POST ${BASE}/api/shots \\\n  -H "Content-Type: application/json" \\\n  -d '{"date":"2026-04-09","maker":"Scott","coffee_id":1,"dose_weight":18.5}'`,
      },
      {
        method: "PUT",
        path: "/api/shots/:id",
        description: "Update a shot. All fields optional.",
        curl: `curl -X PUT ${BASE}/api/shots/42 \\\n  -H "Content-Type: application/json" \\\n  -d '{"grind_setting":"2.5","notes":"slightly under"}'`,
      },
      {
        method: "DELETE",
        path: "/api/shots/:id",
        description: "Delete a shot. Also removes associated video and telemetry files if present.",
        curl: `curl -X DELETE ${BASE}/api/shots/42`,
      },
      {
        method: "POST",
        path: "/api/shots/:id/video",
        description: "Upload a pull video (multipart/form-data, field: file). Replaces existing video.",
        curl: `curl -X POST ${BASE}/api/shots/42/video \\\n  -F "file=@pull.mp4"`,
      },
      {
        method: "DELETE",
        path: "/api/shots/:id/video",
        description: "Remove the video for a shot.",
        curl: `curl -X DELETE ${BASE}/api/shots/42/video`,
      },
      {
        method: "POST",
        path: "/api/shots/:id/telemetry",
        description: "Upload a Beanconqueror flow-profile JSON (multipart/form-data, field: file). Replaces existing telemetry.",
        curl: `curl -X POST ${BASE}/api/shots/42/telemetry \\\n  -F "file=@flowprofile.json"`,
      },
      {
        method: "DELETE",
        path: "/api/shots/:id/telemetry",
        description: "Remove the telemetry file for a shot.",
        curl: `curl -X DELETE ${BASE}/api/shots/42/telemetry`,
      },
    ],
  },
  {
    label: "Grinders",
    value: "grinders",
    endpoints: [
      {
        method: "GET",
        path: "/api/grinders",
        description: "List all grinders sorted by make/model.",
        curl: `curl ${BASE}/api/grinders | jq '.[] | {id, make, model}'`,
      },
      {
        method: "GET",
        path: "/api/grinders/:id",
        description: "Get a grinder by ID.",
        curl: `curl ${BASE}/api/grinders/1`,
      },
      {
        method: "POST",
        path: "/api/grinders",
        description: "Create a grinder.",
        params: [
          { name: "make", type: "string", required: true, description: "Manufacturer" },
          { name: "model", type: "string", required: true, description: "Model name" },
          { name: "type", type: "enum", required: true, description: "flat | conical | blade" },
          { name: "notes", type: "string", required: false, description: "Free-text notes" },
        ],
        curl: `curl -X POST ${BASE}/api/grinders \\\n  -H "Content-Type: application/json" \\\n  -d '{"make":"Niche","model":"Zero","type":"conical"}'`,
      },
      {
        method: "PUT",
        path: "/api/grinders/:id",
        description: "Update a grinder. All fields optional.",
        curl: `curl -X PUT ${BASE}/api/grinders/1 \\\n  -H "Content-Type: application/json" \\\n  -d '{"notes":"purchased 2025"}'`,
      },
      {
        method: "DELETE",
        path: "/api/grinders/:id",
        description: "Delete a grinder. Returns 409 if shots reference it.",
        curl: `curl -X DELETE ${BASE}/api/grinders/1`,
      },
    ],
  },
  {
    label: "Brewing Devices",
    value: "brewing-devices",
    endpoints: [
      {
        method: "GET",
        path: "/api/brewing-devices",
        description: "List all brewing devices sorted by make/model.",
        curl: `curl ${BASE}/api/brewing-devices | jq '.[] | {id, make, model}'`,
      },
      {
        method: "GET",
        path: "/api/brewing-devices/:id",
        description: "Get a brewing device by ID.",
        curl: `curl ${BASE}/api/brewing-devices/1`,
      },
      {
        method: "POST",
        path: "/api/brewing-devices",
        description: "Create a brewing device.",
        params: [
          { name: "make", type: "string", required: true, description: "Manufacturer" },
          { name: "model", type: "string", required: true, description: "Model name" },
          { name: "type", type: "string", required: true, description: "e.g. espresso, drip, aeropress" },
          { name: "warmup_minutes", type: "float", required: false, description: "Warmup time in minutes" },
          { name: "notes", type: "string", required: false, description: "Free-text notes" },
        ],
        curl: `curl -X POST ${BASE}/api/brewing-devices \\\n  -H "Content-Type: application/json" \\\n  -d '{"make":"Decent","model":"DE1","type":"espresso","warmup_minutes":20}'`,
      },
      {
        method: "PUT",
        path: "/api/brewing-devices/:id",
        description: "Update a brewing device. All fields optional.",
        curl: `curl -X PUT ${BASE}/api/brewing-devices/1 \\\n  -H "Content-Type: application/json" \\\n  -d '{"warmup_minutes":15}'`,
      },
      {
        method: "DELETE",
        path: "/api/brewing-devices/:id",
        description: "Delete a brewing device. Returns 409 if shots reference it.",
        curl: `curl -X DELETE ${BASE}/api/brewing-devices/1`,
      },
    ],
  },
  {
    label: "Scales",
    value: "scales",
    endpoints: [
      {
        method: "GET",
        path: "/api/scales",
        description: "List all scales sorted by make/model.",
        curl: `curl ${BASE}/api/scales | jq '.[] | {id, make, model}'`,
      },
      {
        method: "GET",
        path: "/api/scales/:id",
        description: "Get a scale by ID.",
        curl: `curl ${BASE}/api/scales/1`,
      },
      {
        method: "POST",
        path: "/api/scales",
        description: "Create a scale.",
        params: [
          { name: "make", type: "string", required: true, description: "Manufacturer" },
          { name: "model", type: "string", required: true, description: "Model name" },
          { name: "notes", type: "string", required: false, description: "Free-text notes" },
        ],
        curl: `curl -X POST ${BASE}/api/scales \\\n  -H "Content-Type: application/json" \\\n  -d '{"make":"Acaia","model":"Pearl"}'`,
      },
      {
        method: "PUT",
        path: "/api/scales/:id",
        description: "Update a scale. All fields optional.",
        curl: `curl -X PUT ${BASE}/api/scales/1 \\\n  -H "Content-Type: application/json" \\\n  -d '{"notes":"needs calibration"}'`,
      },
      {
        method: "DELETE",
        path: "/api/scales/:id",
        description: "Delete a scale. Returns 409 if shots reference it.",
        curl: `curl -X DELETE ${BASE}/api/scales/1`,
      },
    ],
  },
  {
    label: "Reports",
    value: "reports",
    endpoints: [
      {
        method: "GET",
        path: "/api/reports/dose-yield",
        description: "Dose vs yield ratio over time. All filters optional.",
        params: [
          { name: "date_from", type: "date (ISO)", required: false, description: "Inclusive start date" },
          { name: "date_to", type: "date (ISO)", required: false, description: "Inclusive end date" },
          { name: "coffee_id", type: "integer", required: false, description: "Filter by coffee" },
          { name: "grinder_id", type: "integer", required: false, description: "Filter by grinder" },
          { name: "device_id", type: "integer", required: false, description: "Filter by brewing device" },
        ],
        curl: `curl "${BASE}/api/reports/dose-yield?coffee_id=1&date_from=2026-01-01"`,
      },
      {
        method: "GET",
        path: "/api/reports/shots-per-day",
        description: "Shot count grouped by date. All filters optional.",
        params: [
          { name: "date_from", type: "date (ISO)", required: false, description: "Inclusive start date" },
          { name: "date_to", type: "date (ISO)", required: false, description: "Inclusive end date" },
          { name: "coffee_id", type: "integer", required: false, description: "Filter by coffee" },
          { name: "grinder_id", type: "integer", required: false, description: "Filter by grinder" },
          { name: "device_id", type: "integer", required: false, description: "Filter by brewing device" },
        ],
        curl: `curl "${BASE}/api/reports/shots-per-day?date_from=2026-01-01"`,
      },
      {
        method: "GET",
        path: "/api/reports/extraction-trends",
        description: "Extraction time over time. All filters optional.",
        params: [
          { name: "date_from", type: "date (ISO)", required: false, description: "Inclusive start date" },
          { name: "date_to", type: "date (ISO)", required: false, description: "Inclusive end date" },
          { name: "coffee_id", type: "integer", required: false, description: "Filter by coffee" },
          { name: "grinder_id", type: "integer", required: false, description: "Filter by grinder" },
          { name: "device_id", type: "integer", required: false, description: "Filter by brewing device" },
        ],
        curl: `curl "${BASE}/api/reports/extraction-trends?coffee_id=1"`,
      },
      {
        method: "GET",
        path: "/api/reports/grind-regression",
        description:
          "Bivariate linear regression of grind setting vs days-since-roast and grinder temp. Returns per-grinder coefficients, R², and data points. Requires at least 3 usable shots.",
        params: [
          { name: "coffee_id", type: "integer", required: true, description: "Coffee bag to analyse" },
          { name: "grinder_id", type: "integer", required: false, description: "Restrict to one grinder" },
        ],
        curl: `curl "${BASE}/api/reports/grind-regression?coffee_id=1"`,
      },
      {
        method: "GET",
        path: "/api/reports/target-shot-time",
        description:
          "Weighted moving average of (extraction_time + extraction_delta) across espresso-based shots (americano, latte, cappuccino). Recent shots are weighted more heavily.",
        params: [
          { name: "coffee_id", type: "integer", required: true, description: "Coffee bag to analyse" },
          { name: "grinder_id", type: "integer", required: false, description: "Further filter by grinder" },
          { name: "device_id", type: "integer", required: false, description: "Further filter by brewing device" },
        ],
        curl: `curl "${BASE}/api/reports/target-shot-time?coffee_id=1"`,
      },
      {
        method: "GET",
        path: "/api/reports/by-coffee/:id",
        description: "Aggregate stats and full shot list scoped to one coffee bag.",
        params: [
          { name: "date_from", type: "date (ISO)", required: false, description: "Inclusive start date" },
          { name: "date_to", type: "date (ISO)", required: false, description: "Inclusive end date" },
        ],
        curl: `curl "${BASE}/api/reports/by-coffee/1"`,
      },
    ],
  },
  {
    label: "Grind Model",
    value: "grind-model",
    endpoints: [
      {
        method: "POST",
        path: "/api/reports/grind-model/train",
        description:
          "Fit (or re-fit) the multivariate grind model for a grinder using alternating OLS. " +
          "The model equation is: grind = a0·(temp−65) + a2·(time−target) + a3·(dose−20) + " +
          "a4·age_days + a5·(yield−2·dose) + c(coffee). " +
          "Training uses americano, latte, and cappuccino shots only; excludes first-day shots per coffee. " +
          "Warm-starts intercepts from the most recent prior training. " +
          "Returns 201 with the training record on success.",
        params: [
          {
            name: "grinder_id",
            type: "integer",
            required: true,
            description: "Grinder to train the model for",
          },
        ],
        curl: `curl -X POST "${BASE}/api/reports/grind-model/train?grinder_id=1"`,
      },
      {
        method: "GET",
        path: "/api/reports/grind-model/params",
        description:
          "Retrieve grind model parameters for a grinder. Returns the most recent training by default. " +
          "Includes all model coefficients, per-coffee intercepts, per-coffee target shot times, " +
          "and a data-point array for plotting. Use training_id or as_of to retrieve a historical snapshot.",
        params: [
          {
            name: "grinder_id",
            type: "integer",
            required: true,
            description: "Grinder whose model to fetch",
          },
          {
            name: "training_id",
            type: "integer",
            required: false,
            description: "Return this specific training run",
          },
          {
            name: "as_of",
            type: "date (ISO)",
            required: false,
            description: "Return the most recent training on or before this date",
          },
        ],
        curl: `curl "${BASE}/api/reports/grind-model/params?grinder_id=1"`,
      },
    ],
  },
];

function EndpointRow({ ep }: { ep: Endpoint }) {
  return (
    <Stack gap="xs" py="xs">
      <Group gap="sm" wrap="nowrap">
        <MethodBadge method={ep.method} />
        <Code fz="sm">{ep.path}</Code>
      </Group>
      <Text size="sm" c="dimmed">
        {ep.description}
      </Text>
      {ep.params && ep.params.length > 0 && (
        <Table fz="xs" withTableBorder withColumnBorders>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Param</Table.Th>
              <Table.Th>Type</Table.Th>
              <Table.Th>Required</Table.Th>
              <Table.Th>Description</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {ep.params.map((p) => (
              <Table.Tr key={p.name}>
                <Table.Td>
                  <Code fz="xs">{p.name}</Code>
                </Table.Td>
                <Table.Td>{p.type}</Table.Td>
                <Table.Td>{p.required ? "yes" : "—"}</Table.Td>
                <Table.Td>{p.description}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
      {ep.curl && (
        <Code block fz="xs">
          {ep.curl}
        </Code>
      )}
    </Stack>
  );
}

export default function ApiDocsPage() {
  return (
    <Stack gap="md">
      <Title order={2}>API Reference</Title>
      <Text size="sm" c="dimmed">
        All endpoints are prefixed with <Code>/api</Code> unless noted. Dates
        use ISO 8601 format (<Code>YYYY-MM-DD</Code>).
      </Text>

      <Alert icon={<IconInfoCircle size={16} />} title="Authentication" color="blue" variant="light">
        When <Code>API_KEY</Code> is configured, every <Code>/api/*</Code> request must include either an{" "}
        <Code>X-API-Key: &lt;key&gt;</Code> header or an <Code>?api_key=&lt;key&gt;</Code> query
        parameter. Requests without a valid key receive <Code>401 Unauthorized</Code>. Auth is
        disabled when <Code>API_KEY</Code> is unset.
      </Alert>

      <Alert icon={<IconInfoCircle size={16} />} title="Finding IDs" color="gray" variant="light">
        To look up IDs before calling filtered endpoints:
        <Code block fz="xs" mt="xs">
          {`curl ${BASE}/api/coffees | jq '.[] | {id, name, roaster}'
curl ${BASE}/api/grinders | jq '.[] | {id, make, model}'
curl ${BASE}/api/brewing-devices | jq '.[] | {id, make, model}'
curl ${BASE}/api/scales | jq '.[] | {id, make, model}'`}
        </Code>
      </Alert>

      <Accordion variant="separated" multiple defaultValue={["health"]}>
        {sections.map((section) => (
          <Accordion.Item key={section.value} value={section.value}>
            <Accordion.Control>
              <Text fw={600}>{section.label}</Text>
            </Accordion.Control>
            <Accordion.Panel>
              <Stack gap={0}>
                {section.endpoints.map((ep, i) => (
                  <div key={`${ep.method}-${ep.path}`}>
                    {i > 0 && <Divider my="xs" />}
                    <EndpointRow ep={ep} />
                  </div>
                ))}
              </Stack>
            </Accordion.Panel>
          </Accordion.Item>
        ))}
      </Accordion>
    </Stack>
  );
}
