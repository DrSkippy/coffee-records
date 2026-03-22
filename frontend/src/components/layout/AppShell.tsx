import {
  AppShell,
  Burger,
  Group,
  NavLink,
  Text,
  useMantineTheme,
} from "@mantine/core";
import { useDisclosure, useMediaQuery } from "@mantine/hooks";
import {
  IconChartBar,
  IconCoffee,
  IconPlus,
  IconSettings,
  IconList,
  IconTarget,
} from "@tabler/icons-react";
import { useEffect, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import api from "../../api/client";

const navItems = [
  { path: "/shots", label: "Shots", icon: IconList },
  { path: "/shots/new", label: "New Shot", icon: IconPlus },
  { path: "/coffees", label: "Coffees", icon: IconCoffee },
  { path: "/equipment", label: "Equipment", icon: IconSettings },
  { path: "/reports", label: "Reports", icon: IconChartBar },
  { path: "/planner", label: "Shot Planner", icon: IconTarget },
];

export default function AppLayout({ children }: { children: ReactNode }) {
  const [opened, { toggle }] = useDisclosure();
  const location = useLocation();
  const navigate = useNavigate();
  const theme = useMantineTheme();
  const isMobile = useMediaQuery(`(max-width: ${theme.breakpoints.sm})`);
  const [apiVersion, setApiVersion] = useState<string>("…");

  useEffect(() => {
    api
      .get<{ version: string }>("/version")
      .then((r) => setApiVersion(r.data.version))
      .catch(() => setApiVersion("?"));
  }, []);

  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{
        width: 200,
        breakpoint: "sm",
        collapsed: { mobile: !opened },
      }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group>
            <Burger
              opened={opened}
              onClick={toggle}
              hiddenFrom="sm"
              size="sm"
            />
            <Text fw={700} size="lg">
              ☕ Coffee Records
            </Text>
          </Group>
          <Group gap="xs">
            <Text size="xs" c="dimmed">
              ui v{__UI_VERSION__}
            </Text>
            <Text size="xs" c="dimmed">
              api v{apiVersion}
            </Text>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="xs">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            label={item.label}
            leftSection={<item.icon size={18} />}
            active={location.pathname === item.path}
            onClick={() => {
              navigate(item.path);
              if (isMobile) toggle();
            }}
          />
        ))}
      </AppShell.Navbar>

      <AppShell.Main>{children}</AppShell.Main>
    </AppShell>
  );
}
