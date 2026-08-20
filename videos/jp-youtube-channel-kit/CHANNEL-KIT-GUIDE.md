# JP YouTube Channel Kit

Sistema visual y sonoro bilingüe para los canales de Juan Pedro Márquez sobre
arquitectura de IA, gobernanza, seguridad y ROI.

## Posicionamiento

- **ES:** IA en producción
- **EN:** AI in Production
- **Promesa:** explicar decisiones complejas con arquitectura, controles y
  evidencia aplicable.
- **Voz:** clara, directa, práctica, técnicamente rigurosa y contraria al hype.
- **Límite:** marca personal de un profesional de Microsoft; no debe parecer un
  canal oficial de Microsoft.

## Sistema de marca

| Token | Valor | Uso |
|---|---|---|
| Deep Navy | `#0A1628` | Autoridad, fondos y estructura |
| Signal Azure | `#4A90E2` | Evidencia, rutas y estados activos |
| Advisor Gold | `#C4A35A` | Criterio experto y decisiones |
| Field Ice | `#F3F9FF` | Superficies editoriales claras |
| Proof Blue | `#EAF2FC` | Tarjetas y anotaciones |
| Slate | `#47607D` | Texto secundario |
| System Ink | `#131E2E` | Marcos y superficies oscuras |

La tipografía principal es **Satoshi 500/700/900**. Los archivos están en
`assets/`. Azure significa evidencia; oro significa criterio. No intercambiar
estos roles.

## Entregables

### Identidad principal

Los idents de 10 segundos están en:

- `../jp-youtube-motion/renders/jp-youtube-ident-es.mp4`
- `../jp-youtube-motion/renders/jp-youtube-ident-en.mp4`

### Movimiento

`motion/` contiene fuentes HyperFrames reutilizables y exportaciones:

| Pieza | Duración | Formato | Uso |
|---|---:|---|---|
| Micro-intro | 3 s | MP4 | Apertura habitual tras el hook |
| End screen | 20 s | MP4 | Vídeo recomendado y suscripción |
| Lower third | 6 s | WebM alpha | Identificación del presentador |
| Evidence callout | 4.5 s | WebM alpha | Fuente, prueba o decisión |
| Chapter card | 2.5 s | MP4 | Arquitectura, gobernanza, seguridad y ROI |

Cada pieza tiene una fuente HTML, variables `language` y, cuando corresponde,
`chapter`. Para regenerar:

```bash
cd videos/jp-youtube-channel-kit/motion
npm run check
npm run render
```

### Estáticos

`static/` contiene 32 fuentes HTML editables y 32 PNG:

- 6 miniaturas en tres familias, ES/EN.
- 2 banners de canal, ES/EN.
- 1 avatar monograma.
- 4 overlays transparentes, ES/EN.
- 8 separadores de capítulo, cuatro temas en ES/EN.
- 8 diagramas técnicos, cuatro sistemas en ES/EN.
- 2 marcos transparentes de demo, ES/EN.
- 1 hoja de contacto para revisión.

Para regenerar:

```bash
python3 videos/jp-youtube-channel-kit/static/generate_assets.py
```

### Sonido

- `audio/jp-sonic-signature.wav`: máster PCM 24-bit, 48 kHz, estéreo.
- `audio/jp-sonic-signature.mp3`: copia ligera a 192 kbps.

Usar la firma solo en apertura, cierre o cambio importante de capítulo. No
repetirla bajo narración.

## Reglas de uso

### Miniaturas

- Una tensión, una cara o diagrama y un color de señal.
- De 3 a 5 palabras; nunca más de 7.
- Deben seguir siendo legibles al 10% de su tamaño.
- No usar caras exageradas, robots, flechas genéricas, collages de logos ni
  gradientes púrpura.

### Episodios

1. Abrir con el problema o la decisión; no abrir con el ident.
2. Insertar el micro-intro después del hook, normalmente entre los segundos 8 y
   20.
3. Mostrar una prueba real antes de la primera conclusión: interfaz, código,
   política, diagrama o fuente.
4. Usar capítulos solo cuando cambie la pregunta, no como decoración.
5. Cerrar con una regla de decisión o acción concreta.
6. Reservar los últimos 20 segundos para la end screen.

### Localización

- Publicar cada episodio en un idioma; no alternar frases ES/EN.
- Mantener la misma estructura visual entre versiones.
- Localizar el texto, no traducirlo palabra por palabra.
- Mantener nombres de producto (`Copilot`, `Entra ID`, `Foundry`) y `ROI`.
- Copy de cierre aprobado: **“Claro. Directo. Con rigor.”**
- English closing copy: **“Calm. Direct. Defensible.”**

## Quality control obligatorio

Antes de publicar cualquier pieza:

1. Ejecutar HyperFrames con `--samples 15 --at-transitions --strict`.
2. Exigir cero desbordamientos de texto, incluso durante entradas y salidas.
3. Verificar el render final, no solo la previsualización.
4. Revisar una hoja de contacto con fotogramas de inicio, transición, estado
   estable y salida.
5. Confirmar safe zones, contraste, ortografía y legibilidad móvil en ES y EN
   por separado.
6. Usar solamente allowances para elementos decorativos; nunca para ocultar un
   fallo de texto.

Las piezas estáticas registran dimensiones, transparencia y hallazgos en
`static/render-report.json`.

## Estructura recomendada de contenido

| Serie | Formato | Objetivo |
|---|---|---|
| Architecture Review | 8–12 min | Explicar el límite que decide |
| Governance in Practice | 8–10 min | Convertir riesgo en controles |
| Build It for Production | 12–20 min | Demostrar una implementación real |
| Field Decision | 45–60 s | Una regla útil para Shorts |
| EMEA Briefing | 6–8 min | Analizar cambios con fecha y fuentes |

La prueba es el lenguaje visual. Cada afirmación importante debe conducir a una
arquitectura, configuración, fuente o resultado observable.
