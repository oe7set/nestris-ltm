<script lang="ts">
  // Placeholder for a camera added in OBS: transparent, optionally framed.
  let { width, height, framed = false }: { width: number; height: number; framed?: boolean } = $props();
</script>

<div class="camera" class:framed style:width="{width}px" style:height="{height}px"></div>

<style>
  .camera {
    flex: none;
    box-sizing: border-box; /* the frame stays inside the given size */
  }
  .camera.framed {
    border: 3px solid var(--frame);
    border-radius: 8px;
    box-shadow: inset 0 0 0 2px #000a;
  }
</style>
