import {
  Autocomplete,
  Button,
  Checkbox,
  FileInput,
  Grid,
  Group,
  NumberInput,
  Select,
  Stack,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { IconVideo } from "@tabler/icons-react";
import { DateInput } from "@mantine/dates";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import dayjs from "dayjs";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getCoffees } from "../api/coffees";
import { getBrewingDevices, getGrinders, getScales } from "../api/equipment";
import { createShot, uploadShotVideo } from "../api/shots";
import type { BrewingDevice, Coffee, Grinder, Scale } from "../types";

interface FormValues {
  date: Date;
  maker: string;
  coffee_id: string;
  dose_weight: number | string;
  pre_infusion_time: string;
  extraction_time: number | string;
  scale_id: string;
  final_weight: number | string;
  drink_type: string;
  grinder_temp_before: number | string;
  grinder_temp_after: number | string;
  wedge: boolean;
  shaker: boolean;
  wdt: boolean;
  flow_taper: boolean;
  notes: string;
  grinder_id: string;
  device_id: string;
}

export default function NewShotPage() {
  const navigate = useNavigate();
  const [coffees, setCoffees] = useState<Coffee[]>([]);
  const [grinders, setGrinders] = useState<Grinder[]>([]);
  const [devices, setDevices] = useState<BrewingDevice[]>([]);
  const [scales, setScales] = useState<Scale[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [videoFile, setVideoFile] = useState<File | null>(null);

  useEffect(() => {
    Promise.all([getCoffees(), getGrinders(), getBrewingDevices(), getScales()]).then(
      ([c, g, d, s]) => {
        setCoffees(c);
        setGrinders(g);
        setDevices(d);
        setScales(s);
      }
    );
  }, []);

  const form = useForm<FormValues>({
    initialValues: {
      date: new Date(),
      maker: "Scott",
      coffee_id: "",
      dose_weight: "",
      pre_infusion_time: "",
      extraction_time: "",
      scale_id: "",
      final_weight: "",
      drink_type: "",
      grinder_temp_before: "",
      grinder_temp_after: "",
      wedge: false,
      shaker: false,
      wdt: false,
      flow_taper: false,
      notes: "",
      grinder_id: "",
      device_id: "",
    },
  });

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
        grinder_id: values.grinder_id ? Number(values.grinder_id) : null,
        device_id: values.device_id ? Number(values.device_id) : null,
      };
      const shot = await createShot(payload);
      if (videoFile) {
        await uploadShotVideo(shot.id, videoFile);
      }
      notifications.show({ message: "Shot logged!", color: "green" });
      navigate("/shots");
    } catch {
      notifications.show({ message: "Failed to save shot", color: "red" });
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

  return (
    <Stack>
      <Title order={2}>New Shot</Title>
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
            <FileInput
              label="Video (optional)"
              placeholder="Select video file…"
              accept="video/mp4,video/quicktime,video/webm,video/x-msvideo,video/x-matroska"
              leftSection={<IconVideo size={16} />}
              value={videoFile}
              onChange={setVideoFile}
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
