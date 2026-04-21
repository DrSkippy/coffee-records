import {
  Anchor,
  Autocomplete,
  Button,
  Checkbox,
  FileInput,
  Grid,
  Group,
  NumberInput,
  Select,
  Slider,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { IconChartLine, IconVideo } from "@tabler/icons-react";
import { DateInput } from "@mantine/dates";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import dayjs from "dayjs";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getCoffees } from "../api/coffees";
import { getBrewingDevices, getGrinders, getScales } from "../api/equipment";
import { deleteShotTelemetry, deleteShotVideo, getShot, updateShot, uploadShotTelemetry, uploadShotVideo } from "../api/shots";
import type { BrewingDevice, Coffee, Grinder, Scale } from "../types";

const VIDEO_BASE_URL = "https://resources.drskippy.app/coffee";
const TELEMETRY_BASE_URL = "https://resources.drskippy.app/coffee/telemetry";

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

export default function EditShotPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [coffees, setCoffees] = useState<Coffee[]>([]);
  const [grinders, setGrinders] = useState<Grinder[]>([]);
  const [devices, setDevices] = useState<BrewingDevice[]>([]);
  const [scales, setScales] = useState<Scale[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [sliderPosition, setSliderPosition] = useState(0);
  const [existingVideo, setExistingVideo] = useState<string | null>(null);
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [removeVideo, setRemoveVideo] = useState(false);
  const [existingTelemetry, setExistingTelemetry] = useState<string | null>(null);
  const [telemetryFile, setTelemetryFile] = useState<File | null>(null);
  const [removeTelemetry, setRemoveTelemetry] = useState(false);

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
  });

  useEffect(() => {
    const shotId = Number(id);
    Promise.all([
      getShot(shotId),
      getCoffees(),
      getGrinders(),
      getBrewingDevices(),
      getScales(),
    ])
      .then(([shot, c, g, d, s]) => {
        setCoffees(c);
        setGrinders(g);
        setDevices(d);
        setScales(s);
        setExistingVideo(shot.video_filename);
        setExistingTelemetry(shot.telemetry_filename);
        const delta = shot.extraction_delta ?? 0;
        setSliderPosition(valueToPos(delta));
        form.setValues({
          date: dayjs(shot.date).toDate(),
          maker: shot.maker,
          coffee_id: shot.coffee_id ? String(shot.coffee_id) : "",
          dose_weight: shot.dose_weight ?? "",
          pre_infusion_time: shot.pre_infusion_time ?? "",
          extraction_time: shot.extraction_time ?? "",
          extraction_delta: delta,
          scale_id: shot.scale_id ? String(shot.scale_id) : "",
          final_weight: shot.final_weight ?? "",
          drink_type: shot.drink_type ?? "",
          grinder_temp_before: shot.grinder_temp_before ?? "",
          grinder_temp_after: shot.grinder_temp_after ?? "",
          wedge: shot.wedge,
          shaker: shot.shaker,
          wdt: shot.wdt,
          flow_taper: shot.flow_taper,
          grind_setting: shot.grind_setting ?? "",
          notes: shot.notes ?? "",
          grinder_id: shot.grinder_id ? String(shot.grinder_id) : "",
          device_id: shot.device_id ? String(shot.device_id) : "",
        });
      })
      .catch(() => {
        notifications.show({ message: "Shot not found", color: "red" });
        navigate("/shots");
      })
      .finally(() => setLoading(false));
  }, [id]);

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
        coffee_id: values.coffee_id ? Number(values.coffee_id) : null,
        dose_weight: values.dose_weight !== "" ? Number(values.dose_weight) : null,
        pre_infusion_time: values.pre_infusion_time || null,
        extraction_time: values.extraction_time !== "" ? Number(values.extraction_time) : null,
        scale_id: values.scale_id ? Number(values.scale_id) : null,
        final_weight: values.final_weight !== "" ? Number(values.final_weight) : null,
        drink_type: (values.drink_type || null) as
          | "americano"
          | "latte"
          | "cappuccino"
          | "drip"
          | null,
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
      const shotId = Number(id);
      await updateShot(shotId, payload);
      if (removeVideo) {
        await deleteShotVideo(shotId);
      } else if (videoFile) {
        await uploadShotVideo(shotId, videoFile);
      }
      if (removeTelemetry) {
        await deleteShotTelemetry(shotId);
      } else if (telemetryFile) {
        await uploadShotTelemetry(shotId, telemetryFile);
      }
      notifications.show({ message: "Shot updated!", color: "green" });
      navigate("/shots");
    } catch {
      notifications.show({ message: "Failed to update shot", color: "red" });
    } finally {
      setSubmitting(false);
    }
  };

  const coffeeData = coffees.map((c) => ({
    value: String(c.id),
    label: `${c.name} — ${c.roaster}`,
  }));
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

  if (loading) {
    return <Text>Loading…</Text>;
  }

  return (
    <Stack>
      <Group align="baseline" gap="xs">
        <Title order={2}>Edit Shot</Title>
        <Text c="dimmed" size="sm">#{id}</Text>
      </Group>
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
            <Autocomplete
              label="Maker"
              required
              data={["Scott", "Sara"]}
              {...form.getInputProps("maker")}
            />
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
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <TextInput
              label="Grind Setting"
              placeholder="e.g. 8+5 1/2 or 19.5"
              {...form.getInputProps("grind_setting")}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 4 }}>
            <NumberInput
              label="Dose (g)"
              decimalScale={1}
              step={0.1}
              min={0}
              {...form.getInputProps("dose_weight")}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 4 }}>
            <NumberInput
              label="Final Weight (g)"
              decimalScale={1}
              step={0.1}
              min={0}
              {...form.getInputProps("final_weight")}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 4 }}>
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
            <Textarea label="Notes" rows={3} {...form.getInputProps("notes")} />
          </Grid.Col>
          <Grid.Col span={12}>
            {existingVideo && !removeVideo ? (
              <Stack gap={4}>
                <Text size="sm" fw={500}>
                  Current Video
                </Text>
                <Group gap="xs">
                  <Anchor
                    href={`${VIDEO_BASE_URL}/${existingVideo}`}
                    target="_blank"
                    size="sm"
                  >
                    <Group gap={4}>
                      <IconVideo size={14} />
                      View video
                    </Group>
                  </Anchor>
                  <Button
                    variant="subtle"
                    color="red"
                    size="xs"
                    onClick={() => setRemoveVideo(true)}
                  >
                    Remove
                  </Button>
                </Group>
                <FileInput
                  label="Replace video (optional)"
                  placeholder="Select video file…"
                  accept="video/mp4,video/quicktime,video/webm,video/x-msvideo,video/x-matroska"
                  leftSection={<IconVideo size={16} />}
                  value={videoFile}
                  onChange={setVideoFile}
                  clearable
                />
              </Stack>
            ) : (
              <Stack gap={4}>
                {removeVideo && (
                  <Group gap="xs">
                    <Text size="sm" c="red">
                      Video will be removed on save.
                    </Text>
                    <Button variant="subtle" size="xs" onClick={() => setRemoveVideo(false)}>
                      Undo
                    </Button>
                  </Group>
                )}
                <FileInput
                  label="Video (optional)"
                  placeholder="Select video file…"
                  accept="video/mp4,video/quicktime,video/webm,video/x-msvideo,video/x-matroska"
                  leftSection={<IconVideo size={16} />}
                  value={videoFile}
                  onChange={setVideoFile}
                  clearable
                />
              </Stack>
            )}
          </Grid.Col>
          <Grid.Col span={12}>
            {existingTelemetry && !removeTelemetry ? (
              <Stack gap={4}>
                <Text size="sm" fw={500}>
                  Current Telemetry
                </Text>
                <Group gap="xs">
                  <Anchor
                    href={`${TELEMETRY_BASE_URL}/${existingTelemetry}`}
                    target="_blank"
                    size="sm"
                  >
                    <Group gap={4}>
                      <IconChartLine size={14} />
                      View JSON
                    </Group>
                  </Anchor>
                  <Button
                    variant="subtle"
                    color="red"
                    size="xs"
                    onClick={() => setRemoveTelemetry(true)}
                  >
                    Remove
                  </Button>
                </Group>
                <FileInput
                  label="Replace telemetry JSON (optional)"
                  placeholder="Select Beanconqueror flow profile…"
                  accept=".json,application/json"
                  leftSection={<IconChartLine size={16} />}
                  value={telemetryFile}
                  onChange={setTelemetryFile}
                  clearable
                />
              </Stack>
            ) : (
              <Stack gap={4}>
                {removeTelemetry && (
                  <Group gap="xs">
                    <Text size="sm" c="red">
                      Telemetry will be removed on save.
                    </Text>
                    <Button variant="subtle" size="xs" onClick={() => setRemoveTelemetry(false)}>
                      Undo
                    </Button>
                  </Group>
                )}
                <FileInput
                  label="Telemetry JSON (optional)"
                  placeholder="Select Beanconqueror flow profile…"
                  accept=".json,application/json"
                  leftSection={<IconChartLine size={16} />}
                  value={telemetryFile}
                  onChange={setTelemetryFile}
                  clearable
                />
              </Stack>
            )}
          </Grid.Col>
        </Grid>
        <Group mt="md">
          <Button type="submit" loading={submitting}>
            Save Changes
          </Button>
          <Button variant="subtle" onClick={() => navigate("/shots")}>
            Cancel
          </Button>
        </Group>
      </form>
    </Stack>
  );
}
