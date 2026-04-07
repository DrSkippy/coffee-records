import "@mantine/core/styles.css";
import "@mantine/dates/styles.css";
import "@mantine/notifications/styles.css";
import "@mantine/charts/styles.css";

import { MantineProvider, createTheme } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";

// Cozy Coffee palette:
// Espresso #482E1D | Caramel #895D2B | Leafy #A3966A | Sand Storm #F5DAAE | Cinnamon #90553C
const theme = createTheme({
  primaryColor: "coffee",
  primaryShade: { light: 6, dark: 4 },
  colors: {
    coffee: [
      "#fdf6ee", // 0 - warm cream
      "#f5daae", // 1 - Sand Storm
      "#e8c490", // 2 - light caramel tint
      "#d4a570", // 3 - soft caramel
      "#c08858", // 4 - medium caramel
      "#a3966a", // 5 - Leafy
      "#90553c", // 6 - Cinnamon
      "#895d2b", // 7 - Caramel
      "#5e3820", // 8 - dark brown
      "#482e1d", // 9 - Espresso
    ],
  },
  components: {
    Combobox: {
      styles: {
        dropdown: { backgroundColor: "#e8c490" },
      },
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <MantineProvider theme={theme}>
        <Notifications />
        <App />
      </MantineProvider>
    </BrowserRouter>
  </StrictMode>
);
