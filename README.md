# Multi-Product Exchange Simulator for an Order-Driven Market

A multi-product exchange simulator for a limit order book (LOB) driven
market.

This project extends the simulator introduced in *Burzovní simulátor pro
trh řízený limitními objednávkami* (Kimlová, 2025, University of West
Bohemia).

The objective is to design, implement, secure, and experimentally
validate a multi-asset exchange simulation platform supporting both
autonomous and manual trading agents.

![Web Interface](docs/honicoin_cenzor.png)

------------------------------------------------------------------------

## Project Objectives

The project is based on the following principles:

1.  **Study of existing open-source order-driven exchange simulators**,
    particularly those based on order book processing.
2.  **Design and implementation of an extended simulator** that:
    -   Supports trading of multiple products simultaneously.
    -   Enables interaction of autonomous (algorithmic) and manual
        trading agents.
    -   Allows scalable and distributed deployment.
3.  **Server security hardening**, ensuring full functionality even when
    the source code is publicly available.
4.  **Organization of a student trading competition**, utilizing
    suitable computing infrastructures (e-INFRA CZ, MetaCentrum),
    including:
    -   Collection of simulation data.
    -   Generation of structured statistical reports.
    -   Visualization and cross-product comparison of trading strategy
        performance.
5.  **Comprehensive documentation** of methodologies, design decisions,
    and achieved results.

------------------------------------------------------------------------

## System Architecture

The simulator is modular and consists of the following components:

### Exchange Server

-   Maintains multiple independent order books (one per product).
-   Implements a matching engine based on **price-time priority**.
-   Validates and records incoming orders.
-   Stores simulation state and transaction history.

### Trading Agents

-   Autonomous algorithmic agents (e.g., market maker, liquidity
    provider).
-   Support for custom strategies, including ML-based approaches.
-   Manual trading interface for interactive participation.

### Visualization Layer

-   Real-time monitoring of market activity.
-   Order book depth visualization.
-   Trade history and performance tracking.

### Reporting & Analytics

-   Statistical post-processing of simulation runs.
-   Comparative analysis of strategies.
-   Cross-product performance evaluation.

------------------------------------------------------------------------

## Security Considerations

Special emphasis is placed on:

-   Strict separation of server and client logic.
-   Robust order validation and input sanitization.
-   Prevention of manipulation through protocol-level safeguards.
-   Controlled API exposure and configurable access policies.
-   Ensuring market integrity despite open-source availability.

The system is designed to remain fair, stable, and operational even
under adversarial conditions.

------------------------------------------------------------------------

## Research & Educational Use

The platform enables:

-   Study of market microstructure.
-   Analysis of liquidity formation and price dynamics.
-   Evaluation of trading algorithm stability.
-   Cross-product strategy comparison.
-   Organization of educational exchange simulations.
-   Experimental regulatory and stress-testing scenarios.

------------------------------------------------------------------------

## Technologies Used

-   **Python 3.9+**
-   **Tornado** (asynchronous web server)
-   **Bokeh** (interactive visualization)
-   **NumPy**, **Pandas** (data processing)
-   **Jupyter Notebook** (analysis & reporting)

------------------------------------------------------------------------

## Getting Started

### 1. Clone the Repository

``` bash
git clone https://github.com/Jivl00/limit-order-book-simulator
cd limit-order-book-simulator
```

### 2. Install Dependencies

``` bash
pip install -r requirements.txt
```

### 3. Configuration

Edit: config/server_config.json

You can configure: - Server IP address - Ports - API endpoints - Product
definitions - Simulation parameters

------------------------------------------------------------------------

### 4. Start the Exchange Server

``` bash
cd src
python server/server.py
```

To resume a previous simulation state:

``` bash
python server/server.py -l
```

Simulation data are stored in: data/

------------------------------------------------------------------------

### 5. Run Trading Agents

Example:

``` bash
python server/agents/market_maker.py
python server/agents/liquidity_generator.py
```

Custom agents can be implemented in:

client/agents/

------------------------------------------------------------------------

### 6. Launch the Web Interface

``` bash
python viz/main_page.py
```

Access via:

http://`<IP_ADDRESS>`:`<VIZ_PORT>`

------------------------------------------------------------------------

## Simulation Analysis

Open the reporting notebook:

viz/report/report.ipynb

The notebook allows:

-   Strategy performance comparison
-   Volume and trade frequency analysis
-   Statistical summary generation
-   Visualization of price evolution and liquidity metrics

![Strategy Comparison](docs/best_traders_plot.png)

------------------------------------------------------------------------

## Running Tests

``` bash
cd tests
python -m unittest tests.py
```

------------------------------------------------------------------------

## Reference

Kimlová, V. (2025).\
*Burzovní simulátor pro trh řízený limitními objednávkami*.\
University of West Bohemia, Faculty of Applied Sciences.\
Supervisor: J. Pospíšil.

------------------------------------------------------------------------

## Documentation

-   Trading manual: docs/Trading_manual.pdf
-   Thesis document: docs/dp_2024_25_KIMLOVÁ_Vladimíra.pdf
-   Poster: docs/DP_poster.pdf
-   Visualization documentation: docs/VI.pdf
