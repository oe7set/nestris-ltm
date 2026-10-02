import { mount } from "svelte";
import "./app.css";
import App from "./App.svelte";
import { i18n } from "./lib/i18n.svelte";

document.documentElement.lang = i18n.locale;

const target = document.getElementById("app");
if (!target) throw new Error("#app missing");

export default mount(App, { target });
