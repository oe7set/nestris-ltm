import { mount } from "svelte";
import "./overlay.css";
import App from "./App.svelte";

const target = document.getElementById("app");
if (!target) throw new Error("#app missing");

export default mount(App, { target });
