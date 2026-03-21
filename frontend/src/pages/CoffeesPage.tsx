import {
  ActionIcon,
  Badge,
  Button,
  Group,
  Modal,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { IconPencil, IconTrash } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { createCoffee, deleteCoffee, getCoffees, updateCoffee } from "../api/coffees";
import type { Coffee } from "../types";

interface CoffeeForm {
  name: string;
  roaster: string;
  roast_date: string;
  origin_country: string;
  roast_level: string;
  variety: string;
  process: string;
}

export default function CoffeesPage() {
  const [coffees, setCoffees] = useState<Coffee[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Coffee | null>(null);

  const form = useForm<CoffeeForm>({
    initialValues: {
      name: "",
      roaster: "",
      roast_date: "",
      origin_country: "",
      roast_level: "",
      variety: "",
      process: "",
    },
  });

  const load = () => getCoffees().then(setCoffees);
  useEffect(() => { load(); }, []);

  const openCreate = () => {
    setEditing(null);
    form.reset();
    setModalOpen(true);
  };

  const openEdit = (c: Coffee) => {
    setEditing(c);
    form.setValues({
      name: c.name,
      roaster: c.roaster,
      roast_date: c.roast_date ?? "",
      origin_country: c.origin_country ?? "",
      roast_level: c.roast_level ?? "",
      variety: c.variety ?? "",
      process: c.process ?? "",
    });
    setModalOpen(true);
  };

  const handleSubmit = async (values: CoffeeForm) => {
    const payload = {
      ...values,
      roast_date: values.roast_date || null,
      origin_country: values.origin_country || null,
      roast_level: (values.roast_level || null) as Coffee["roast_level"],
      variety: values.variety || null,
      process: values.process || null,
    };
    try {
      if (editing) {
        await updateCoffee(editing.id, payload);
      } else {
        await createCoffee(payload);
      }
      setModalOpen(false);
      load();
    } catch {
      notifications.show({ message: "Save failed", color: "red" });
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteCoffee(id);
      load();
    } catch (err: unknown) {
      const status = (err as { response?: { status: number } })?.response?.status;
      notifications.show({
        message: status === 409 ? "Cannot delete: shots reference this coffee" : "Delete failed",
        color: "red",
      });
    }
  };

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Coffees</Title>
        <Button onClick={openCreate}>+ Add Coffee</Button>
      </Group>

      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Name</Table.Th>
            <Table.Th>Roaster</Table.Th>
            <Table.Th>Roast Date</Table.Th>
            <Table.Th>Level</Table.Th>
            <Table.Th>Origin</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {coffees.map((c) => (
            <Table.Tr key={c.id}>
              <Table.Td>{c.name}</Table.Td>
              <Table.Td>{c.roaster}</Table.Td>
              <Table.Td>{c.roast_date ?? "—"}</Table.Td>
              <Table.Td>
                {c.roast_level ? (
                  <Badge size="sm">{c.roast_level}</Badge>
                ) : (
                  "—"
                )}
              </Table.Td>
              <Table.Td>{c.origin_country ?? "—"}</Table.Td>
              <Table.Td>
                <Group gap="xs">
                  <ActionIcon variant="subtle" onClick={() => openEdit(c)}>
                    <IconPencil size={16} />
                  </ActionIcon>
                  <ActionIcon
                    variant="subtle"
                    color="red"
                    onClick={() => handleDelete(c.id)}
                  >
                    <IconTrash size={16} />
                  </ActionIcon>
                </Group>
              </Table.Td>
            </Table.Tr>
          ))}
          {coffees.length === 0 && (
            <Table.Tr>
              <Table.Td colSpan={6}>
                <Text c="dimmed" ta="center">
                  No coffees yet
                </Text>
              </Table.Td>
            </Table.Tr>
          )}
        </Table.Tbody>
      </Table>

      <Modal
        opened={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editing ? "Edit Coffee" : "Add Coffee"}
      >
        <form onSubmit={form.onSubmit(handleSubmit)}>
          <Stack>
            <TextInput label="Name" required {...form.getInputProps("name")} />
            <TextInput label="Roaster" required {...form.getInputProps("roaster")} />
            <TextInput
              label="Roast Date"
              placeholder="YYYY-MM-DD"
              {...form.getInputProps("roast_date")}
            />
            <Select
              label="Roast Level"
              data={["light", "medium", "dark"]}
              clearable
              {...form.getInputProps("roast_level")}
            />
            <TextInput label="Origin Country" {...form.getInputProps("origin_country")} />
            <TextInput label="Variety" {...form.getInputProps("variety")} />
            <TextInput
              label="Process"
              placeholder="washed / natural / honey"
              {...form.getInputProps("process")}
            />
            <Button type="submit">{editing ? "Update" : "Create"}</Button>
          </Stack>
        </form>
      </Modal>
    </Stack>
  );
}
