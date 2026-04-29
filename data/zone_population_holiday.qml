<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis styleCategories="AllStyleCategories" version="3.22.0">
  <flags>
    <Identifiable>1</Identifiable>
    <Removable>1</Removable>
    <Searchable>1</Searchable>
    <Private>0</Private>
  </flags>
  <!-- 時系列アニメーション設定
       QGIS メニュー: レイヤプロパティ → 時間 で確認・変更可能
       Temporal Controller パネルからアニメーション再生 -->
  <temporal enabled="1" accumulate="0" mode="2" limitMode="0"
            durationUnit="min" fixedDuration="0"
            startField="start_time" endField="end_time"
            startExpression="" endExpression="" durationField="">
    <fixedRange>
      <start>2022-10-16T00:00:00</start>
      <end>2022-10-17T00:00:00</end>
    </fixedRange>
  </temporal>
  <renderer-v2 attr="population" graduatedMode="Jenks"
               enableOrderBy="0" symbollevels="0"
               type="graduatedSymbol" forceraster="0" referencescale="-1">
    <ranges>
      <range render="true" symbol="0" label="0 〜 100"     lower="0"    upper="100"   uuid="{0}"/>
      <range render="true" symbol="1" label="100 〜 300"   lower="100"  upper="300"   uuid="{1}"/>
      <range render="true" symbol="2" label="300 〜 700"   lower="300"  upper="700"   uuid="{2}"/>
      <range render="true" symbol="3" label="700 〜 1500"  lower="700"  upper="1500"  uuid="{3}"/>
      <range render="true" symbol="4" label="1500 〜 3000" lower="1500" upper="3000"  uuid="{4}"/>
      <range render="true" symbol="5" label="3000 〜 8000" lower="3000" upper="8000"  uuid="{5}"/>
    </ranges>
    <symbols>
      <!-- 0〜100: 濃青 -->
      <symbol clip_to_extent="1" name="0" type="fill" alpha="0.85" force_rhr="0">
        <data_defined_properties>
          <Option type="Map"><Option name="name" type="QString" value=""/><Option name="properties"/><Option name="type" type="QString" value="collection"/></Option>
        </data_defined_properties>
        <layer class="SimpleFill" enabled="1" pass="0" locked="0">
          <Option type="Map">
            <Option name="border_width_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
            <Option name="color"                       type="QString" value="49,54,149,217"/>
            <Option name="joinstyle"                   type="QString" value="miter"/>
            <Option name="offset"                      type="QString" value="0,0"/>
            <Option name="offset_map_unit_scale"       type="QString" value="3x:0,0,0,0,0,0"/>
            <Option name="offset_unit"                 type="QString" value="MM"/>
            <Option name="outline_color"               type="QString" value="180,180,180,120"/>
            <Option name="outline_style"               type="QString" value="solid"/>
            <Option name="outline_width"               type="QString" value="0.1"/>
            <Option name="outline_width_unit"          type="QString" value="MM"/>
            <Option name="style"                       type="QString" value="solid"/>
          </Option>
        </layer>
      </symbol>
      <!-- 100〜300: 青 -->
      <symbol clip_to_extent="1" name="1" type="fill" alpha="0.85" force_rhr="0">
        <data_defined_properties>
          <Option type="Map"><Option name="name" type="QString" value=""/><Option name="properties"/><Option name="type" type="QString" value="collection"/></Option>
        </data_defined_properties>
        <layer class="SimpleFill" enabled="1" pass="0" locked="0">
          <Option type="Map">
            <Option name="border_width_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
            <Option name="color"                       type="QString" value="69,117,180,217"/>
            <Option name="joinstyle"                   type="QString" value="miter"/>
            <Option name="offset"                      type="QString" value="0,0"/>
            <Option name="offset_map_unit_scale"       type="QString" value="3x:0,0,0,0,0,0"/>
            <Option name="offset_unit"                 type="QString" value="MM"/>
            <Option name="outline_color"               type="QString" value="180,180,180,120"/>
            <Option name="outline_style"               type="QString" value="solid"/>
            <Option name="outline_width"               type="QString" value="0.1"/>
            <Option name="outline_width_unit"          type="QString" value="MM"/>
            <Option name="style"                       type="QString" value="solid"/>
          </Option>
        </layer>
      </symbol>
      <!-- 300〜700: 水色 -->
      <symbol clip_to_extent="1" name="2" type="fill" alpha="0.85" force_rhr="0">
        <data_defined_properties>
          <Option type="Map"><Option name="name" type="QString" value=""/><Option name="properties"/><Option name="type" type="QString" value="collection"/></Option>
        </data_defined_properties>
        <layer class="SimpleFill" enabled="1" pass="0" locked="0">
          <Option type="Map">
            <Option name="border_width_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
            <Option name="color"                       type="QString" value="116,173,209,217"/>
            <Option name="joinstyle"                   type="QString" value="miter"/>
            <Option name="offset"                      type="QString" value="0,0"/>
            <Option name="offset_map_unit_scale"       type="QString" value="3x:0,0,0,0,0,0"/>
            <Option name="offset_unit"                 type="QString" value="MM"/>
            <Option name="outline_color"               type="QString" value="180,180,180,120"/>
            <Option name="outline_style"               type="QString" value="solid"/>
            <Option name="outline_width"               type="QString" value="0.1"/>
            <Option name="outline_width_unit"          type="QString" value="MM"/>
            <Option name="style"                       type="QString" value="solid"/>
          </Option>
        </layer>
      </symbol>
      <!-- 700〜1500: 黄 -->
      <symbol clip_to_extent="1" name="3" type="fill" alpha="0.85" force_rhr="0">
        <data_defined_properties>
          <Option type="Map"><Option name="name" type="QString" value=""/><Option name="properties"/><Option name="type" type="QString" value="collection"/></Option>
        </data_defined_properties>
        <layer class="SimpleFill" enabled="1" pass="0" locked="0">
          <Option type="Map">
            <Option name="border_width_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
            <Option name="color"                       type="QString" value="254,224,144,217"/>
            <Option name="joinstyle"                   type="QString" value="miter"/>
            <Option name="offset"                      type="QString" value="0,0"/>
            <Option name="offset_map_unit_scale"       type="QString" value="3x:0,0,0,0,0,0"/>
            <Option name="offset_unit"                 type="QString" value="MM"/>
            <Option name="outline_color"               type="QString" value="180,180,180,120"/>
            <Option name="outline_style"               type="QString" value="solid"/>
            <Option name="outline_width"               type="QString" value="0.1"/>
            <Option name="outline_width_unit"          type="QString" value="MM"/>
            <Option name="style"                       type="QString" value="solid"/>
          </Option>
        </layer>
      </symbol>
      <!-- 1500〜3000: オレンジ -->
      <symbol clip_to_extent="1" name="4" type="fill" alpha="0.85" force_rhr="0">
        <data_defined_properties>
          <Option type="Map"><Option name="name" type="QString" value=""/><Option name="properties"/><Option name="type" type="QString" value="collection"/></Option>
        </data_defined_properties>
        <layer class="SimpleFill" enabled="1" pass="0" locked="0">
          <Option type="Map">
            <Option name="border_width_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
            <Option name="color"                       type="QString" value="244,109,67,217"/>
            <Option name="joinstyle"                   type="QString" value="miter"/>
            <Option name="offset"                      type="QString" value="0,0"/>
            <Option name="offset_map_unit_scale"       type="QString" value="3x:0,0,0,0,0,0"/>
            <Option name="offset_unit"                 type="QString" value="MM"/>
            <Option name="outline_color"               type="QString" value="180,180,180,120"/>
            <Option name="outline_style"               type="QString" value="solid"/>
            <Option name="outline_width"               type="QString" value="0.1"/>
            <Option name="outline_width_unit"          type="QString" value="MM"/>
            <Option name="style"                       type="QString" value="solid"/>
          </Option>
        </layer>
      </symbol>
      <!-- 3000〜8000: 赤 -->
      <symbol clip_to_extent="1" name="5" type="fill" alpha="0.85" force_rhr="0">
        <data_defined_properties>
          <Option type="Map"><Option name="name" type="QString" value=""/><Option name="properties"/><Option name="type" type="QString" value="collection"/></Option>
        </data_defined_properties>
        <layer class="SimpleFill" enabled="1" pass="0" locked="0">
          <Option type="Map">
            <Option name="border_width_map_unit_scale" type="QString" value="3x:0,0,0,0,0,0"/>
            <Option name="color"                       type="QString" value="215,48,39,217"/>
            <Option name="joinstyle"                   type="QString" value="miter"/>
            <Option name="offset"                      type="QString" value="0,0"/>
            <Option name="offset_map_unit_scale"       type="QString" value="3x:0,0,0,0,0,0"/>
            <Option name="offset_unit"                 type="QString" value="MM"/>
            <Option name="outline_color"               type="QString" value="180,180,180,120"/>
            <Option name="outline_style"               type="QString" value="solid"/>
            <Option name="outline_width"               type="QString" value="0.1"/>
            <Option name="outline_width_unit"          type="QString" value="MM"/>
            <Option name="style"                       type="QString" value="solid"/>
          </Option>
        </layer>
      </symbol>
    </symbols>
    <source-symbol>
      <symbol clip_to_extent="1" name="0" type="fill" alpha="0.85" force_rhr="0">
        <data_defined_properties>
          <Option type="Map"><Option name="name" type="QString" value=""/><Option name="properties"/><Option name="type" type="QString" value="collection"/></Option>
        </data_defined_properties>
        <layer class="SimpleFill" enabled="1" pass="0" locked="0">
          <Option type="Map">
            <Option name="color"         type="QString" value="49,54,149,217"/>
            <Option name="outline_color" type="QString" value="180,180,180,120"/>
            <Option name="outline_width" type="QString" value="0.1"/>
            <Option name="style"         type="QString" value="solid"/>
          </Option>
        </layer>
      </symbol>
    </source-symbol>
    <colorramp name="[source]" type="gradient">
      <Option type="Map">
        <Option name="color1"    type="QString" value="49,54,149,255"/>
        <Option name="color2"    type="QString" value="215,48,39,255"/>
        <Option name="direction" type="QString" value="ccw"/>
        <Option name="discrete"  type="QString" value="0"/>
        <Option name="rampType"  type="QString" value="gradient"/>
        <Option name="stops"     type="QString" value="0.2;69,117,180,255;rgb;ccw:0.4;116,173,209,255;rgb;ccw:0.6;254,224,144,255;rgb;ccw:0.8;244,109,67,255;rgb;ccw"/>
      </Option>
    </colorramp>
    <classificationMethod id="Jenks">
      <symmetricMode enabled="0" astride="0" symmetrypoint="0"/>
      <labelFormat format="%1 〜 %2" trimtrailingzeroes="1" labelprecision="0"/>
      <parameters/>
      <extraInformation/>
    </classificationMethod>
    <rotation/>
    <sizescale/>
  </renderer-v2>
  <customproperties>
    <Option/>
  </customproperties>
  <blendMode>0</blendMode>
  <featureBlendMode>0</featureBlendMode>
  <layerOpacity>1</layerOpacity>
</qgis>
