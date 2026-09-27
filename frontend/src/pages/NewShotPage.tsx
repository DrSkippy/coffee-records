import {
  Alert,
  Button,
  Checkbox,
  FileInput,
  Grid,
  Group,
  NumberInput,
  Progress,
  Select,
  Slider,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { IconChartLine, IconFileImport, IconVideo } from "@tabler/icons-react";
import { DateInput } from "@mantine/dates";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import dayjs from "dayjs";
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { createCoffee, getCoffees } from "../api/coffees";
import { getDefaults } from "../api/defaults";
import { getBrewingDevices, getGrinders, getScales } from "../api/equipment";
import { createShot, getMakers, uploadShotTelemetry, uploadShotVideo } from "../api/shots";
import MakerSelect from "../components/shots/MakerSelect";
import { defaultMakerAt } from "../utils/makers";
import type { BrewingDevice, Coffee, Grinder, Scale, ShotCsvImport } from "../types";

const posToValue = (pos: number): number => {
  if (pos === 0) return 0;
  return Math.sign(pos) * (Math.exp((Math.abs(pos) / 15) * Math.log(16)) - 1);
};

const valueToPos = (val: number): number => {
  if (val === 0) return 0;
  return Math.sign(val) * (Math.log(Math.abs(val) + 1) / Math.log(16)) * 15;
};

const DELTA_MARKS = [
  { value: -15, label: "-15" },
  { value: valueToPos(-5), label: "-5" },
  { value: valueToPos(-1), label: "-1" },
  { value: 0, label: "0" },
  { value: valueToPos(1), label: "1" },
  { value: valueToPos(5), label: "5" },
  { value: 15, label: "15" },
];

// Coffee select value for a coffee proposed by a CSV import, created on save.
const NEW_COFFEE = "__new__";

const oneDecimal = (value: number): number => Math.round(value * 10) / 10;

interface FormValues {
  date: Date;
  maker: string;
  coffee_id: string;
  dose_weight: number | string;
  pre_infusion_time: string;
  extraction_time: number | string;
  extraction_delta: number;
  scale_id: string;
  final_weight: number | string;
  drink_type: string;
  grinder_temp_before: number | string;
  grinder_temp_after: number | string;
  wedge: boolean;
  shaker: boolean;
  wdt: boolean;
  flow_taper: boolean;
  grind_setting: string;
  notes: string;
  grinder_id: string;
  device_id: string;
}

export default function NewShotPage() {
  const navigate = useNavigate();
  const csvImport =
    (useLocation().state as { csvImport?: ShotCsvImport } | null)?.csvImport ?? null;
  const createdCoffeeId = useRef<number | null>(null);
  const [coffees, setCoffees] = useState<Coffee[]>([]);
  const [grinders, setGrinders] = useState<Grinder[]>([]);
  const [devices, setDevices] = useState<BrewingDevice[]>([]);
  const [scales, setScales] = useState<Scale[]>([]);
  const [makers, setMakers] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [videoUploadProgress, setVideoUploadProgress] = useState<number | null>(null);
  const [telemetryFile, setTelemetryFile] = useState<File | null>(() =>
    csvImport?.telemetry && csvImport.telemetry_filename
      ? new File([JSON.stringify(csvImport.telemetry)], csvImport.telemetry_filename, {
          type: "application/json",
        })
      : null
  );
  const [sliderPosition, setSliderPosition] = useState(0);

  useEffect(() => {
    getMakers().then(setMakers);
    Promise.all([getCoffees(), getGrinders(), getBrewingDevices(), getScales(), getDefaults()]).then(
      ([c, g, d, s, defaults]) => {
        setCoffees(c);
        setGrinders(g);
        setDevices(d);
        setScales(s);

        form.setValues({
          maker: defaultMakerAt(new Date()),
          dose_weight: defaults.dose_weight ?? "",
          pre_infusion_time: defaults.pre_infusion_time ?? "",
          extraction_time: defaults.extraction_time ?? "",
          final_weight: defaults.final_weight ?? "",
          drink_type: defaults.drink_type ?? "",
          grinder_temp_before: defaults.grinder_temp_before ?? "",
          wedge: defaults.wedge,
          shaker: defaults.shaker,
          wdt: defaults.wdt,
          flow_taper: defaults.flow_taper,
        });

        // Default to most recently entered coffee (API returns sorted by date desc)
        if (c.length > 0) form.setFieldValue("coffee_id", String(c[0].id));

        const grinder = g.find((x) =>
          `${x.make} ${x.model}`.toLowerCase().includes("option-o")
        );
        if (grinder) form.setFieldValue("grinder_id", String(grinder.id));

        const device = d.find((x) =>
          `${x.make} ${x.model}`.toLowerCase().includes("synchronika")
        );
        if (device) form.setFieldValue("device_id", String(device.id));

        const scale = s.find((x) =>
          `${x.make} ${x.model}`.toLowerCase().includes("bookoo")
        );
        if (scale) form.setFieldValue("scale_id", String(scale.id));

        if (csvImport) applyCsvImport(csvImport);
      }
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load once; Mantine's form object isn't referentially stable
  }, []);

  const form = useForm<FormValues>({
    initialValues: {
      date: new Date(),
      maker: "",
      coffee_id: "",
      dose_weight: "",
      pre_infusion_time: "",
      extraction_time: "",
      extraction_delta: 0,
      scale_id: "",
      final_weight: "",
      drink_type: "",
      grinder_temp_before: "",
      grinder_temp_after: "",
      wedge: false,
      shaker: false,
      wdt: false,
      flow_taper: false,
      grind_setting: "",
      notes: "",
      grinder_id: "",
      device_id: "",
    },
    validate: {
      grind_setting: (value, values) => {
        if (!value) return null;
        const selectedGrinder = grinders.find((g) => String(g.id) === values.grinder_id);
        if (!selectedGrinder) return null;
        const name = `${selectedGrinder.make} ${selectedGrinder.model}`.toLowerCase();
        if (name.includes("mazzer")) {
          return /^\d+\+\d+( \d+\/\d+)?$/.test(value)
            ? null
            : 'Expected format: "#+# #/#" or "#+#" (e.g. "8+5 1/2" or "8+5")';
        }
        if (
          name.includes("option-o") ||
          name.includes("timemore") ||
          name.includes("baratza")
        ) {
          return /^\d+(\.\d+)?$/.test(value)
            ? null
            : "Expected a single number (e.g. 19.5)";
        }
        return null;
      },
    },
  });

  const applyCsvImport = ({ fields, new_coffee, notes }: ShotCsvImport) => {
    if (fields.date) form.setFieldValue("date", dayjs(fields.date).toDate());
    // Operator from the CSV wins; otherwise default by when the shot was pulled.
    if (fields.maker) form.setFieldValue("maker", fields.maker);
    else if (fields.recorded_at)
      form.setFieldValue("maker", defaultMakerAt(dayjs(fields.recorded_at).toDate()));
    if (fields.dose_weight) form.setFieldValue("dose_weight", oneDecimal(fields.dose_weight));
    if (fields.final_weight) form.setFieldValue("final_weight", oneDecimal(fields.final_weight));
    if (fields.extraction_time) form.setFieldValue("extraction_time", fields.extraction_time);
    if (fields.pre_infusion_time) form.setFieldValue("pre_infusion_time", fields.pre_infusion_time);
    if (fields.grind_setting) form.setFieldValue("grind_setting", fields.grind_setting);
    if (fields.grinder_id) form.setFieldValue("grinder_id", String(fields.grinder_id));
    if (fields.device_id) form.setFieldValue("device_id", String(fields.device_id));
    if (fields.coffee_id) form.setFieldValue("coffee_id", String(fields.coffee_id));
    else if (new_coffee) form.setFieldValue("coffee_id", NEW_COFFEE);
    form.setFieldValue("notes", notes);
  };

  const resolveCoffeeId = async (value: string): Promise<number | null> => {
    if (value !== NEW_COFFEE) return value ? Number(value) : null;
    if (createdCoffeeId.current === null && csvImport?.new_coffee) {
      createdCoffeeId.current = (await createCoffee(csvImport.new_coffee)).id;
    }
    return createdCoffeeId.current;
  };

  const handleDeltaSlider = (pos: number) => {
    setSliderPosition(pos);
    form.setFieldValue("extraction_delta", Math.round(posToValue(pos) * 10) / 10);
  };

  const handleSubmit = async (values: FormValues) => {
    setSubmitting(true);
    try {
      const payload = {
        date: dayjs(values.date).format("YYYY-MM-DD"),
        maker: values.maker,
        coffee_id: await resolveCoffeeId(values.coffee_id),
        dose_weight: values.dose_weight !== "" ? Number(values.dose_weight) : null,
        pre_infusion_time: values.pre_infusion_time || null,
        extraction_time: values.extraction_time !== "" ? Number(values.extraction_time) : null,
        scale_id: values.scale_id ? Number(values.scale_id) : null,
        final_weight: values.final_weight !== "" ? Number(values.final_weight) : null,
        drink_type: (values.drink_type || null) as "americano" | "latte" | "cappuccino" | "drip" | null,
        grinder_temp_before:
          values.grinder_temp_before !== "" ? Number(values.grinder_temp_before) : null,
        grinder_temp_after:
          values.grinder_temp_after !== "" ? Number(values.grinder_temp_after) : null,
        wedge: values.wedge,
        shaker: values.shaker,
        wdt: values.wdt,
        flow_taper: values.flow_taper,
        notes: values.notes || null,
        grind_setting: values.grind_setting || null,
        extraction_delta: values.extraction_delta,
        grinder_id: values.grinder_id ? Number(values.grinder_id) : null,
        device_id: values.device_id ? Number(values.device_id) : null,
      };
      const shot = await createShot(payload);
      if (videoFile) {
        setVideoUploadProgress(0);
        await uploadShotVideo(shot.id, videoFile, setVideoUploadProgress);
        setVideoUploadProgress(null);
      }
      if (telemetryFile) {
        await uploadShotTelemetry(shot.id, telemetryFile);
      }
      notifications.show({ message: "Shot logged!", color: "green" });
      navigate("/shots");
    } catch {
      setVideoUploadProgress(null);
      notifications.show({ message: "Failed to save shot", color: "red" });
    } finally {
      setSubmitting(false);
    }
  };

  const coffeeData = coffees.map((c) => ({
    value: String(c.id),
    label: `${c.name} — ${c.roaster}`,
  }));
  if (csvImport?.new_coffee) {
    const { name, roaster, roast_date } = csvImport.new_coffee;
    coffeeData.unshift({
      value: NEW_COFFEE,
      label: `New: ${name} — ${roaster}${roast_date ? ` (roasted ${roast_date})` : ""}`,
    });
  }
  const grinderData = grinders.map((g) => ({
    value: String(g.id),
    label: `${g.make} ${g.model}`,
  }));
  const deviceData = devices.map((d) => ({
    value: String(d.id),
    label: `${d.make} ${d.model}`,
  }));
  const scaleData = scales.map((s) => ({
    value: String(s.id),
    label: `${s.make} ${s.model}`,
  }));

  return (
    <Stack>
      <Title order={2}>New Shot</Title>
      {csvImport && (
        <Alert
          icon={<IconFileImport size={16} />}
          color={csvImport.warnings.length ? "yellow" : "blue"}
          title={`Imported from ${csvImport.source}`}
        >
          {csvImport.warnings.length === 0 ? (
            <Text size="sm">Review the prefilled fields, then save.</Text>
          ) : (
            csvImport.warnings.map((w) => (
              <Text key={w} size="sm">
                {w}
              </Text>
            ))
          )}
        </Alert>
      )}
      <form onSubmit={form.onSubmit(handleSubmit)}>
        <Grid gutter="sm">
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <DateInput
              label="Date"
              required
              valueFormat="YYYY-MM-DD"
              {...form.getInputProps("date")}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <MakerSelect required knownMakers={makers} {...form.getInputProps("maker")} />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <Select
              label="Coffee"
              data={coffeeData}
              searchable
              clearable
              {...form.getInputProps("coffee_id")}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <Select
              label="Drink Type"
              data={["americano", "latte", "cappuccino", "drip"]}
              clearable
              {...form.getInputProps("drink_type")}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <TextInput
              label="Grind Setting"
              placeholder="e.g. 8+5 1/2 or 19.5"
              {...form.getInputProps("grind_setting")}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <NumberInput
              label="Dose (g)"
              decimalScale={1}
              step={0.1}
              min={0}
              {...form.getInputProps("dose_weight")}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <NumberInput
              label="Final Weight (g)"
              decimalScale={1}
              step={0.1}
              min={0}
              {...form.getInputProps("final_weight")}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <NumberInput
              label="Extraction Time (s)"
              decimalScale={1}
              step={0.5}
              min={0}
              {...form.getInputProps("extraction_time")}
            />
          </Grid.Col>
          <Grid.Col span={12}>
            <Stack gap={4}>
              <Group justify="space-between">
                <Text size="sm" fw={500}>
                  Extraction Delta (s)
                </Text>
                <Text
                  size="sm"
                  fw={700}
                  c={
                    form.values.extraction_delta > 0
                      ? "blue"
                      : form.values.extraction_delta < 0
                        ? "red"
                        : "dimmed"
                  }
                >
                  {form.values.extraction_delta === 0
                    ? "0s"
                    : form.values.extraction_delta > 0
                      ? `+${form.values.extraction_delta.toFixed(1)}s`
                      : `${form.values.extraction_delta.toFixed(1)}s`}
                </Text>
              </Group>
              <Text size="xs" c="dimmed">
                Estimate: seconds to add (+) or subtract (−) for ideal extraction
              </Text>
              <Slider
                styles={{
                  bar: {
                    width:
                      sliderPosition === 0
                        ? 0
                        : `calc(${(Math.abs(sliderPosition) / 30) * 100}% + 2 * var(--slider-size))`,
                    insetInlineStart:
                      sliderPosition >= 0
                        ? `calc(50% - var(--slider-size))`
                        : `calc(${((sliderPosition + 15) / 30) * 100}% - var(--slider-size))`,
                  },
                }}
                value={sliderPosition}
                onChange={handleDeltaSlider}
                min={-15}
                max={15}
                step={0.01}
                marks={DELTA_MARKS}
                label={null}
                mb="md"
              />
            </Stack>
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <NumberInput
              label="Grinder Temp Before (°F)"
              decimalScale={1}
              {...form.getInputProps("grinder_temp_before")}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <NumberInput
              label="Grinder Temp After (°F)"
              decimalScale={1}
              {...form.getInputProps("grinder_temp_after")}
            />
          </Grid.Col>
          <Grid.Col span={12}>
            <Textarea label="Notes" rows={3} {...form.getInputProps("notes")} />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <Select
              label="Grinder"
              data={grinderData}
              searchable
              clearable
              {...form.getInputProps("grinder_id")}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <Select
              label="Machine"
              data={deviceData}
              searchable
              clearable
              {...form.getInputProps("device_id")}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <Select
              label="Scale"
              data={scaleData}
              searchable
              clearable
              {...form.getInputProps("scale_id")}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <TextInput
              label="Pre-Infusion Time"
              placeholder="e.g. 5+5"
              {...form.getInputProps("pre_infusion_time")}
            />
          </Grid.Col>
          <Grid.Col span={12}>
            <Group>
              <Checkbox label="Wedge" {...form.getInputProps("wedge", { type: "checkbox" })} />
              <Checkbox label="Shaker" {...form.getInputProps("shaker", { type: "checkbox" })} />
              <Checkbox label="WDT" {...form.getInputProps("wdt", { type: "checkbox" })} />
              <Checkbox
                label="Flow Taper"
                {...form.getInputProps("flow_taper", { type: "checkbox" })}
              />
            </Group>
          </Grid.Col>
          <Grid.Col span={12}>
            <Stack gap={4}>
              <FileInput
                label="Video (optional)"
                placeholder="Select video file…"
                accept="video/mp4,video/quicktime,video/webm,video/x-msvideo,video/x-matroska"
                leftSection={<IconVideo size={16} />}
                value={videoFile}
                onChange={setVideoFile}
                clearable
              />
              {videoUploadProgress !== null && (
                <Progress value={videoUploadProgress} size="sm" animated={videoUploadProgress < 100} />
              )}
            </Stack>
          </Grid.Col>
          <Grid.Col span={12}>
            <FileInput
              label="Telemetry JSON (optional)"
              placeholder="Select Beanconqueror flow profile…"
              accept=".json,application/json"
              leftSection={<IconChartLine size={16} />}
              value={telemetryFile}
              onChange={setTelemetryFile}
              clearable
            />
          </Grid.Col>
        </Grid>
        <Group mt="md">
          <Button type="submit" loading={submitting}>
            Save Shot
          </Button>
          <Button variant="subtle" onClick={() => navigate("/shots")}>
            Cancel
          </Button>
        </Group>
      </form>
    </Stack>
  );
}
