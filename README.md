<a id="readme-top"></a>

<!-- ESCUDOS DO PROJETO -->

[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![MIT License][license-shield]][license-url]
[![LinkedIn][linkedin-shield]][linkedin-url]

<!-- LOGOTIPO DO PROJETO -->
<br />
<div align="center">
  <a href="https://github.com/alissonpef/Spot-Spraying-Polygons">
    <img src="assets/logo.png" alt="Logo" width="120" height="120">
  </a>

  <h3 align="center">Spot Spraying Polygons</h3>

  <p align="center">
    Geração automática de polígonos de pulverização georreferenciados para o manejo localizado de plantas daninhas na agricultura de precisão.
    <br />
    <a href="https://github.com/alissonpef/Spot-Spraying-Polygons"><strong>Explore a documentação »</strong></a>
    <br />
    <br />
    <a href="https://github.com/alissonpef/Spot-Spraying-Polygons/issues/new?labels=bug">Reportar Bug</a>
    &middot;
    <a href="https://github.com/alissonpef/Spot-Spraying-Polygons/issues/new?labels=enhancement">Solicitar Recurso</a>
  </p>
</div>

<!-- ÍNDICE -->
<details>
  <summary>Índice</summary>
  <ol>
    <li>
      <a href="#sobre-o-projeto">Sobre O Projeto</a>
      <ul>
        <li><a href="#construído-com">Construído Com</a></li>
      </ul>
    </li>
    <li>
      <a href="#começando">Começando</a>
      <ul>
        <li><a href="#pré-requisitos">Pré-requisitos</a></li>
        <li><a href="#instalação">Instalação</a></li>
      </ul>
    </li>
    <li><a href="#uso">Uso</a></li>
    <li><a href="#contribuindo">Contribuindo</a></li>
    <li><a href="#licença">Licença</a></li>
    <li><a href="#contato">Contato</a></li>
  </ol>
</details>

<!-- SOBRE O PROJETO -->

## Sobre O Projeto

O **Spot Spraying Polygons** é uma ferramenta desenvolvida para resolver um problema crucial na agricultura moderna: o desperdício de defensivos agrícolas. A aplicação de produtos químicos em área total de forma indiscriminada gera prejuízos financeiros e ambientais. Esta ferramenta permite converter mapas de detecção georreferenciada de plantas invasoras em mapas de prescrição precisos, minimizando a área de aplicação.

O pipeline de processamento consiste em:
- **Projeção UTM automática**: Reprojeta as coordenadas geográficas (WGS84) para um sistema métrico (UTM) local, otimizando as medições reais em metros.
- **Buffer e Agrupamento (Clustering)**: Expande a área de cada planta invasora com base em uma margem de segurança configurável e agrupa manchas próximas para formar polígonos de tratamento coerentes.
- **9 Algoritmos de Cobertura**: Oferece estratégias geométricas inteligentes (como *Minimum Rotated Rectangle*, *Boustrophedon Cellular Decomposition*, *Fixed Grid*, *Quadtree*, *Strips*, entre outras) para se adaptar a diferentes formatos de talhões e tipos de aplicação.
- **Evasão de Obstáculos**: Permite informar áreas que não devem ser pulverizadas (árvores, construções, etc.), subtraindo-as com margens de segurança específicas.
- **Exportação Universal**: Exporta os mapas resultantes no formato padrão GeoJSON, amplamente compatível com drones agrícolas e controladores de pulverização.
- **Roteamento de Linhas e Métricas**: Gera linhas de pulverização no padrão zigue-zague com algoritmos de caminhos mínimos (Dijkstra) para conectar as passadas, além de fornecer um relatório completo de eficiência (IoU, curvas, área desperdiçada).

O projeto acompanha tanto uma interface de linha de comando (CLI) quanto um painel web interativo (Streamlit) para visualização geográfica das etapas.

<p align="right">(<a href="#readme-top">voltar ao topo</a>)</p>

### Construído Com

Esta seção lista as principais tecnologias, linguagens e bibliotecas que dão suporte ao projeto.

* [![Python][Python-shield]][Python-url]
* [![Shapely][Shapely-shield]][Shapely-url]
* [![GeoPandas][GeoPandas-shield]][GeoPandas-url]
* [![Streamlit][Streamlit-shield]][Streamlit-url]
* [![Folium][Folium-shield]][Folium-url]
* [![NumPy][NumPy-shield]][NumPy-url]
* [![SciPy][SciPy-shield]][SciPy-url]
* [![Pandas][Pandas-shield]][Pandas-url]

<p align="right">(<a href="#readme-top">voltar ao topo</a>)</p>

<!-- COMEÇANDO -->

## Começando

Para rodar o projeto localmente em seu ambiente de desenvolvimento, siga os passos abaixo.

### Pré-requisitos

Este projeto exige Python 3.11 ou superior. Recomendamos a utilização do gerenciador de pacotes **uv** para uma instalação extremamente rápida e isolada.

- Instalar o **uv** (caso ainda não possua):
  ```sh
  pip install uv
  ```

### Instalação

1. Clone o repositório:
   ```sh
   git clone https://github.com/alissonpef/Spot-Spraying-Polygons.git
   cd Spot-Spraying-Polygons
   ```
2. Instale as dependências e crie o ambiente virtual com o **uv**:
   ```sh
   uv sync
   ```
3. Ative o ambiente virtual:
   - **Linux/macOS**:
     ```sh
     source .venv/bin/activate
     ```
   - **Windows**:
     ```sh
     .venv\Scripts\activate
     ```

<p align="right">(<a href="#readme-top">voltar ao topo</a>)</p>

<!-- EXEMPLOS DE USO -->

## Uso

O projeto oferece suporte para execução visual ou via terminal.

### Painel Interativo (Streamlit)

Para iniciar o painel de visualização web no navegador:
```sh
uv run streamlit run src/ui/app.py
```
*(ou utilize o atalho configurado `uv run ui`)*

Na interface você poderá arrastar seus próprios arquivos GeoJSON ou usar as amostras salvas na pasta `data/`, ajustar os parâmetros geométricos em tempo real, remover polígonos indesejados diretamente no mapa e fazer o download do GeoJSON final pronto.

### Linha de Comando (CLI)

1. **Geração de Polígonos**:
   ```sh
   uv run spot-spray \
     --weeds data/input/weed1.geojson data/input/weed2.geojson \
     --fields data/input/fields.geojson \
     --obstacles data/input/obstacles.geojson \
     --output data/output/spraying-mrr.geojson \
     --coverage_method mrr \
     --weed_buffer_m 1.5 \
     --merge_distance_m 8.0
   ```

2. **Geração de Linhas de Pulverização**:
   ```sh
   uv run spraying-lines data/output/spraying-mrr.geojson 2.0 0.0 --output-dir data/output/lines
   ```

3. **Execução de Métricas**:
   ```sh
   uv run metrics
   ```

<p align="right">(<a href="#readme-top">voltar ao topo</a>)</p>

<!-- CONTRIBUINDO -->

## Contribuindo

Contribuições são o que tornam a comunidade open source um lugar tão incrível para aprender, inspirar e criar. Qualquer contribuição que você fizer será **muito apreciada**.

Se você tiver alguma sugestão para melhorar o projeto, sinta-se à vontade para fazer o fork do repositório e abrir um Pull Request, ou criar uma issue com a tag "enhancement".

1. Faça o Fork do Projeto
2. Crie a sua Branch de Funcionalidade (`git checkout -b feature/FuncionalidadeIncrivel`)
3. Commit suas Mudanças (`git commit -m 'Adicione alguma FuncionalidadeIncrivel'`)
4. Faça o Push para a Branch (`git push origin feature/FuncionalidadeIncrivel`)
5. Abra um Pull Request

### Principais contribuidores:

<a href="https://github.com/alissonpef/Spot-Spraying-Polygons/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=alissonpef/Spot-Spraying-Polygons" alt="imagem contrib.rocks" />
</a>

<p align="right">(<a href="#readme-top">voltar ao topo</a>)</p>

<!-- LICENÇA -->

## Licença

Distribuído sob a Licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais informações.

<p align="right">(<a href="#readme-top">voltar ao topo</a>)</p>

<!-- CONTATO -->

## Contrato

Alisson Pereira Ferreira - alissonpef@gmail.com - [LinkedIn](https://www.linkedin.com/in/alisson-pereira-ferreira/)

Link do Projeto: [https://github.com/alissonpef/Spot-Spraying-Polygons](https://github.com/alissonpef/Spot-Spraying-Polygons)

<p align="right">(<a href="#readme-top">voltar ao topo</a>)</p>

---

Made with ❤️ by **Alisson Pereira**.

<!-- MARKDOWN LINKS & IMAGES -->
[contributors-shield]: https://img.shields.io/github/contributors/alissonpef/Spot-Spraying-Polygons.svg?style=for-the-badge
[contributors-url]: https://github.com/alissonpef/Spot-Spraying-Polygons/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/alissonpef/Spot-Spraying-Polygons.svg?style=for-the-badge
[forks-url]: https://github.com/alissonpef/Spot-Spraying-Polygons/network/members
[stars-shield]: https://img.shields.io/github/stars/alissonpef/Spot-Spraying-Polygons.svg?style=for-the-badge
[stars-url]: https://github.com/alissonpef/Spot-Spraying-Polygons/stargazers
[issues-shield]: https://img.shields.io/github/issues/alissonpef/Spot-Spraying-Polygons.svg?style=for-the-badge
[issues-url]: https://github.com/alissonpef/Spot-Spraying-Polygons/issues
[license-shield]: https://img.shields.io/github/license/alissonpef/Spot-Spraying-Polygons.svg?style=for-the-badge
[license-url]: https://github.com/alissonpef/Spot-Spraying-Polygons/blob/main/LICENSE
[linkedin-shield]: https://img.shields.io/badge/-LinkedIn-black.svg?style=for-the-badge&logo=linkedin&colorB=555
[linkedin-url]: https://www.linkedin.com/in/alisson-pereira-ferreira/

[Python-shield]: https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white
[Python-url]: https://www.python.org/
[Shapely-shield]: https://img.shields.io/badge/Shapely-2E8B57?style=for-the-badge
[Shapely-url]: https://shapely.readthedocs.io/
[GeoPandas-shield]: https://img.shields.io/badge/GeoPandas-139C5A?style=for-the-badge
[GeoPandas-url]: https://geopandas.org/
[Streamlit-shield]: https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white
[Streamlit-url]: https://streamlit.io/
[Folium-shield]: https://img.shields.io/badge/Folium-77B829?style=for-the-badge
[Folium-url]: https://python-visualization.github.io/folium/
[NumPy-shield]: https://img.shields.io/badge/NumPy-013243?style=for-the-badge&logo=numpy&logoColor=white
[NumPy-url]: https://numpy.org/
[SciPy-shield]: https://img.shields.io/badge/SciPy-8CAAE6?style=for-the-badge&logo=scipy&logoColor=white
[SciPy-url]: https://scipy.org/
[Pandas-shield]: https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white
[Pandas-url]: https://pandas.pydata.org/