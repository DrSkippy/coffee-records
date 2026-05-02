import {
  Autocomplete,
  Button,
  Checkbox,
  Grid,
  Group,
  NumberInput,
  Select,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";
import { getDefaults, updateDefaults } from "../api/defaults";

interface FormValues {
  maker: string;
  dose_weight: number | string;
  pre_infusion_time: string;
  extraction_time: number | string;
  final_weight: number | string;
  drink_type: string;
  grinder_temp_before: number | string;
  wedge: boolean;
  shaker: boolean;
  wdt: boolean;
  flow_taper: boolean;
}

export default function DefaultsPage() {
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const form = useForm<FormValues>({
    initialValues: {
      maker: "",
      dose_weight: "",
      pre_infusion_time: "",
      extraction_time: "",
      final_weight: "",
      drink_type: "",
      grinder_temp_before: "",
      wedge: false,
      shaker: false,
      wdt: false,
      flow_taper: false,
    },
  });

  useEffect(() => {
    getDefaults()
      .then((defaults) => {
        form.setValues({
          maker: defaults.maker,
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
      })
      .catch(() => {
        notifications.show({ message: "Failed to load defaults", color: "red" });
      })
      .finally(() => setLoading(false));
  }, []);

  const handleSubmit = async (values: FormValues) => {
    setSubmitting(true);
    try {
      await updateDefaults({
        maker: values.maker,
        dose_weight: values.dose_weight !== "" ? Number(values.dose_weight) : null,
        pre_infusion_time: values.pre_infusion_time || null,
        extraction_time: values.extraction_time !== "" ? Number(values.extraction_time) : null,
        final_weight: values.final_weight !== "" ? Number(values.final_weight) : null,
        drink_type: (values.drink_type || null) as
          | "americano"
          | "latte"
          | "cappuccino"
          | "drip"
          | null,
        grinder_temp_before:
          values.grinder_temp_before !== "" ? Number(values.grinder_temp_before) : null,
        wedge: values.wedge,
        shaker: values.shaker,
        wdt: values.wdt,
        flow_taper: values.flow_taper,
      });
      notifications.show({ message: "Defaults saved!", color: "green" });
    } catch {
      notifications.show({ message: "Failed to save defaults", color: "red" });
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return <Text>Loading…</Text>;
  }

  return (
    <Stack>
      <Title order={2}>Defaults</Title>
      <Text size="sm" c="dimmed">
        These values pre-fill the New Shot form. Change them here whenever your workflow changes.
      </Text>
      <form onSubmit={form.onSubmit(handleSubmit)}>
        <Grid gutter="sm">
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
              label="Drink Type"
              data={["americano", "latte", "cappuccino", "drip"]}
              clearable
              {...form.getInputProps("drink_type")}
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
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <TextInput
              label="Pre-Infusion Time"
              placeholder="e.g. 5+5"
              {...form.getInputProps("pre_infusion_time")}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6 }}>
            <NumberInput
              label="Grinder Temp Before (°F)"
              decimalScale={1}
              {...form.getInputProps("grinder_temp_before")}
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
        </Grid>
        <Group mt="md">
          <Button type="submit" loading={submitting}>
            Save Defaults
          </Button>
        </Group>
      </form>
    </Stack>
  );
}
