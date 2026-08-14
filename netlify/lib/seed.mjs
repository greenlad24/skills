// Seed menu for Vibration, compiled into the functions bundle.
//
// Extracted from the original single-file menu. Images live as real files under
// public/img and are referenced by path. Served only when the Blobs store is
// empty; once the menu is saved from /admin the stored copy always wins.
//
// zoom / focusY are per-image mobile framing. focusY is 5% wherever the subject
// still fits there; four photos with tall subjects need a lower anchor. zoom is
// solved against the hero box each item actually gets (the box is flex-sized,
// so longer text leaves a shorter box). Structural, not text, so the editor
// cannot change them.

export const SEED_MENU = {
  "brand": {
    "tag": "Live Music &middot; Kitchen &middot; Bar",
    "foot": "Koh Samui",
    "logo": "/img/logo.png"
  },
  "sections": [
    {
      "key": "food",
      "title": "Food",
      "sub": "Wings · Bites · Snacks",
      "thumb": "/img/food-thumb.jpg",
      "entries": [
        {
          "type": "item",
          "hero": "/img/food-01.jpg",
          "heroW": 1960,
          "eyebrow": "From the Kitchen",
          "name": "Buffalo Wings",
          "nameclass": "",
          "story": "Crispy, saucy, and made for sharing — or not.",
          "build": "Six Wings / Buffalo Sauce",
          "serve": "With Blue Cheese or Ranch",
          "price": "160",
          "priceHtml": "",
          "zoom": 0.94,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/food-02.jpg",
          "heroW": 2160,
          "eyebrow": "From the Kitchen",
          "name": "French Fries",
          "nameclass": "",
          "story": "Golden, crispy, always a good idea.",
          "build": "Straight-Cut / Sea Salt",
          "serve": "Small or Large",
          "price": "",
          "priceHtml": "<span style=\"display:inline-block; transform:translateX(-25px);\"><small>THB</small>80<span class=\"bar\">|</span>120</span>",
          "zoom": 1.2,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/food-03.jpg",
          "heroW": 2160,
          "eyebrow": "From the Kitchen",
          "name": "Krapow",
          "nameclass": "",
          "story": "Thai holy basil stir-fry, with a fried egg on top.",
          "build": "Stir-Fried Basil / Minced Pork or Chicken",
          "serve": "Add a fried egg +20",
          "price": "",
          "priceHtml": "<span class=\"split\"><span class=\"sz\">BASE</span>120<span class=\"gap\"></span><span class=\"sz\">EGG</span>140</span>",
          "zoom": 1.087,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/food-04.jpg",
          "heroW": 2576,
          "eyebrow": "From the Kitchen",
          "name": "Fried Rice",
          "nameclass": "",
          "story": "Wok-fried, fragrant, and satisfying.",
          "build": "Shrimp or Chicken",
          "serve": "Choose your protein",
          "price": "",
          "priceHtml": "<span class=\"split\"><span class=\"sz\">CHICKEN</span>120<span class=\"gap\"></span><span class=\"sz\">SHRIMP</span>150</span>",
          "zoom": 1.169,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/food-05.jpg",
          "heroW": 2160,
          "eyebrow": "From the Kitchen",
          "name": "Chicken Cashew Nut",
          "nameclass": "",
          "story": "Wok-tossed chicken, cashews, and dried chili.",
          "build": "Chicken / Cashew / Chili",
          "serve": "A Thai favourite",
          "price": "160",
          "priceHtml": "",
          "zoom": 1.049,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/food-06.jpg",
          "heroW": 2367,
          "eyebrow": "From the Kitchen",
          "name": "Fried Spring Rolls",
          "nameclass": "",
          "story": "Crispy, golden, and dangerously moreish.",
          "build": "Crispy Pastry / Vegetable",
          "serve": "Served with sweet chili",
          "price": "120",
          "priceHtml": "",
          "zoom": 1.188,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/food-07.jpg",
          "heroW": 2160,
          "eyebrow": "From the Kitchen",
          "name": "Jalapeno Poppers",
          "nameclass": "",
          "story": "Golden, gooey, with a gentle kick.",
          "build": "Melted Cheese / Jalapeno",
          "serve": "Served with ranch dip",
          "price": "200",
          "priceHtml": "",
          "zoom": 1.2,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/food-08.jpg",
          "heroW": 2160,
          "eyebrow": "From the Kitchen",
          "name": "Mozzarella Sticks",
          "nameclass": "",
          "story": "Crispy outside, endless cheese pull inside.",
          "build": "Breaded / Melted Mozzarella",
          "serve": "Served with marinara",
          "price": "160",
          "priceHtml": "",
          "zoom": 1.127,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/food-09.jpg",
          "heroW": 2160,
          "eyebrow": "From the Kitchen",
          "name": "Wisconsin Fried Cheese Curds",
          "nameclass": "long",
          "story": "A little bit of Wisconsin, deep-fried.",
          "build": "Battered / Cheese Curds",
          "serve": "Served with dipping sauce",
          "price": "240",
          "priceHtml": "",
          "zoom": 1.125,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/food-10.jpg",
          "heroW": 2160,
          "eyebrow": "From the Kitchen",
          "name": "Chilli Lime Peanuts",
          "nameclass": "long",
          "story": "Zesty, spicy, dangerously snackable.",
          "build": "Roasted Peanuts / Chilli / Lime",
          "serve": "The perfect bar snack",
          "price": "120",
          "priceHtml": "",
          "zoom": 1.2,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/food-11.jpg",
          "heroW": 2160,
          "eyebrow": "From the Kitchen",
          "name": "Corn Tempura",
          "nameclass": "",
          "story": "Sweet corn, crispy and light.",
          "build": "Japanese-Style / Sweet Corn",
          "serve": "Served with dipping sauce",
          "price": "110",
          "priceHtml": "",
          "zoom": 1.061,
          "focusY": 5
        },
        {
          "type": "back",
          "kicker": "",
          "quote": "&ldquo;I came for the live music, blacked out on buffalo sauce, and woke up a better person.&rdquo;",
          "stars": true,
          "attrib": "&mdash; probably you, tomorrow morning",
          "fine": ""
        }
      ]
    },
    {
      "key": "cocktails",
      "title": "Cocktails",
      "sub": "Signature · Spirits · Shots",
      "thumb": "/img/cocktails-thumb.jpg",
      "entries": [
        {
          "type": "item",
          "hero": "/img/cocktails-01.jpg",
          "heroW": 2160,
          "eyebrow": "Signature Collection",
          "name": "Japanese Highball",
          "nameclass": "long",
          "story": "Clean, cold, and precise — the art of less.",
          "build": "Japanese Whisky / Soda / Lemon",
          "serve": "Served in the glacier highball",
          "price": "180",
          "priceHtml": "",
          "zoom": 1.132,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/cocktails-02.jpg",
          "heroW": 1944,
          "eyebrow": "Signature Collection",
          "name": "Margarita",
          "nameclass": "",
          "story": "Salt, citrus, and sunshine — the eternal classic.",
          "build": "Tequila / Lime / Triple Sec / Salt",
          "serve": "Served in the crystal martini glass",
          "price": "180",
          "priceHtml": "",
          "zoom": 1.099,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/cocktails-03.jpg",
          "heroW": 2160,
          "eyebrow": "Signature Collection",
          "name": "Mojito",
          "nameclass": "",
          "story": "Havana in a glass — mint, lime, and lift.",
          "build": "White Rum / Lime / Mint / Soda",
          "serve": "Served in the glacier highball",
          "price": "180",
          "priceHtml": "",
          "zoom": 1.151,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/cocktails-04.jpg",
          "heroW": 1944,
          "eyebrow": "Signature Collection",
          "name": "Gin Basil Smash",
          "nameclass": "",
          "story": "Garden-fresh and sharp — green in every sense.",
          "build": "Gin / Lemon / Muddled Basil / Sugar",
          "serve": "Served in the diamond-cut rocks glass",
          "price": "200",
          "priceHtml": "",
          "zoom": 1.088,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/cocktails-05.jpg",
          "heroW": 2160,
          "eyebrow": "Signature Collection",
          "name": "Midori Sour",
          "nameclass": "",
          "story": "Electric green, bright and playful.",
          "build": "Midori / Lemon / Sour",
          "serve": "Served in the footed goblet",
          "price": "200",
          "priceHtml": "",
          "zoom": 1.151,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/cocktails-06.jpg",
          "heroW": 2136,
          "eyebrow": "Signature Collection",
          "name": "Moscow Mule",
          "nameclass": "",
          "story": "A ginger bite with a cool island edge.",
          "build": "Vodka / Lime / Ginger Beer",
          "serve": "Served in the tiki glass",
          "price": "200",
          "priceHtml": "",
          "zoom": 1.116,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/cocktails-07.jpg",
          "heroW": 1780,
          "eyebrow": "Signature Collection",
          "name": "Samui Mule",
          "nameclass": "",
          "story": "Our island's own mule — ginger, lime, and lemongrass.",
          "build": "Vodka / Ginger Beer / Lime / Lemongrass",
          "serve": "Served in the tiki glass",
          "price": "210",
          "priceHtml": "",
          "zoom": 0.999,
          "focusY": 20
        },
        {
          "type": "item",
          "hero": "/img/cocktails-08.jpg",
          "heroW": 1944,
          "eyebrow": "Signature Collection",
          "name": "Espresso Martini",
          "nameclass": "",
          "story": "The midnight pick-me-up, dressed to impress.",
          "build": "Vodka / Coffee Liqueur / Fresh Espresso",
          "serve": "Served in the crystal martini glass",
          "price": "220",
          "priceHtml": "",
          "zoom": 1.121,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/cocktails-09.jpg",
          "heroW": 2160,
          "eyebrow": "Signature Collection",
          "name": "White Russian",
          "nameclass": "",
          "story": "Velvet layers of cream and coffee.",
          "build": "Vodka / Coffee Liqueur / Cream",
          "serve": "Served in the diamond-cut rocks glass",
          "price": "220",
          "priceHtml": "",
          "zoom": 1.187,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/cocktails-10.jpg",
          "heroW": 2160,
          "eyebrow": "Signature Collection",
          "name": "Arnold Palmer",
          "nameclass": "",
          "story": "Smooth iced tea with a grown-up twist.",
          "build": "Vodka / Honey / Black Tea",
          "serve": "Served in the tall glass",
          "price": "220",
          "priceHtml": "",
          "zoom": 1.11,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/cocktails-11.jpg",
          "heroW": 1602,
          "eyebrow": "Signature Collection",
          "name": "Piña Colada",
          "nameclass": "",
          "story": "Creamy, tropical, and pure island escape.",
          "build": "Rum / Coconut Cream / Pineapple",
          "serve": "Served in the barrel glass",
          "price": "240",
          "priceHtml": "",
          "zoom": 0.964,
          "focusY": 36
        },
        {
          "type": "item",
          "hero": "/img/cocktails-12.jpg",
          "heroW": 1780,
          "eyebrow": "Signature Collection",
          "name": "Rum Punch",
          "nameclass": "",
          "story": "A carnival of the tropics in every sip.",
          "build": "Rum / Pineapple / Orange / Grenadine",
          "serve": "Served in the tiki glass",
          "price": "240",
          "priceHtml": "",
          "zoom": 0.901,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/cocktails-13.jpg",
          "heroW": 2160,
          "eyebrow": "Signature Collection",
          "name": "Whiskey Sour",
          "nameclass": "",
          "story": "Bourbon, softened by silk and citrus.",
          "build": "Bourbon / Lemon / Sugar / Bitters",
          "serve": "Served in the diamond-cut rocks glass",
          "price": "240",
          "priceHtml": "",
          "zoom": 1.116,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/cocktails-14.jpg",
          "heroW": 1944,
          "eyebrow": "Signature Collection",
          "name": "T.P.C",
          "nameclass": "",
          "story": "Bold, briny, and dangerously smooth.",
          "build": "Tequila / Pickle Juice / Lime",
          "serve": "Served in the rocks glass",
          "price": "240",
          "priceHtml": "",
          "zoom": 1.133,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/cocktails-15.jpg",
          "heroW": 2160,
          "eyebrow": "Signature Collection",
          "name": "Aperol Spritz",
          "nameclass": "",
          "story": "The golden hour, bottled and bubbling.",
          "build": "Aperol / Prosecco / Soda / Orange",
          "serve": "Served in the wine glass",
          "price": "260",
          "priceHtml": "",
          "zoom": 0.967,
          "focusY": 21
        },
        {
          "type": "item",
          "hero": "/img/cocktails-16.jpg",
          "heroW": 2160,
          "eyebrow": "Signature Collection",
          "name": "Long Island",
          "nameclass": "",
          "story": "Five spirits, one dangerously easy sip.",
          "build": "Vodka / Gin / Rum / Tequila / Cola",
          "serve": "Served in the glacier highball",
          "price": "260",
          "priceHtml": "",
          "zoom": 1.11,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/cocktails-17.jpg",
          "heroW": 2160,
          "eyebrow": "Signature Collection",
          "name": "Negroni",
          "nameclass": "",
          "story": "Bitter, bold, and beautifully Italian.",
          "build": "Gin / Campari / Sweet Vermouth / Orange",
          "serve": "Served in the diamond-cut rocks glass",
          "price": "260",
          "priceHtml": "",
          "zoom": 1.178,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/cocktails-18.jpg",
          "heroW": 1944,
          "eyebrow": "Signature Collection",
          "name": "Cherry Collins",
          "nameclass": "",
          "story": "A sparkling twist on the summer classic.",
          "build": "Gin / Lemon / Cherry / Soda",
          "serve": "Served in the glacier highball",
          "price": "280",
          "priceHtml": "",
          "zoom": 1.132,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/cocktails-19.jpg",
          "heroW": 2160,
          "eyebrow": "Signature Collection",
          "name": "Cherry Grey Espresso Martini",
          "nameclass": "long",
          "story": "Earl Grey and cherry meet the midnight martini.",
          "build": "Earl Grey Vodka / Cherry / Coffee Liqueur / Espresso",
          "serve": "Served in the crystal martini glass",
          "price": "320",
          "priceHtml": "",
          "zoom": 1.107,
          "focusY": 5
        },
        {
          "type": "list",
          "eyebrow": "The Bar",
          "title": "Spirits",
          "col1": [
            {
              "cat": "Vodka",
              "rows": [
                [
                  "Gilbey's",
                  "120",
                  "45ml"
                ],
                [
                  "Kulov",
                  "120",
                  "45ml"
                ],
                [
                  "Kilo",
                  "160",
                  "45ml"
                ],
                [
                  "Absolut",
                  "180",
                  "45ml"
                ],
                [
                  "Tried & True",
                  "180",
                  "45ml"
                ],
                [
                  "Stoli",
                  "200",
                  "45ml"
                ],
                [
                  "Grey Goose",
                  "280",
                  "45ml"
                ],
                [
                  "Grey Goose Cherry",
                  "280",
                  "45ml"
                ],
                [
                  "Ciroc",
                  "340",
                  "45ml"
                ]
              ]
            },
            {
              "cat": "Tequila & Mezcal",
              "rows": [
                [
                  "Pancho Villa",
                  "130",
                  "45ml"
                ],
                [
                  "El Tequileno Blanco",
                  "150",
                  "30ml"
                ],
                [
                  "El Tequileno Still Strength",
                  "300",
                  "30ml"
                ],
                [
                  "El Tequileno Reposado",
                  "320",
                  "45ml"
                ],
                [
                  "Tarantula Azul",
                  "150",
                  ""
                ],
                [
                  "Jose Cuervo Silver",
                  "160",
                  "45ml"
                ],
                [
                  "Los Arcos",
                  "180",
                  "45ml"
                ],
                [
                  "Arette Blanco",
                  "210",
                  "30ml"
                ],
                [
                  "400 Conejos Mezcal",
                  "240",
                  "30ml"
                ],
                [
                  "Don Fulano Reposado",
                  "260",
                  "30ml"
                ],
                [
                  "La Travesia Mezcal",
                  "260",
                  "45ml"
                ],
                [
                  "Creyente Mezcal",
                  "270",
                  "45ml"
                ],
                [
                  "Cascahuin Blanco",
                  "310",
                  "45ml"
                ]
              ]
            }
          ],
          "col2": [
            {
              "cat": "Gin",
              "rows": [
                [
                  "Gilbey's London Dry",
                  "120",
                  "45ml"
                ],
                [
                  "Tanqueray London Dry",
                  "150",
                  "45ml"
                ],
                [
                  "Gordon's London Dry",
                  "160",
                  "45ml"
                ],
                [
                  "Bombay Sapphire",
                  "180",
                  "45ml"
                ],
                [
                  "Rogue Farmhouse",
                  "180",
                  "45ml"
                ],
                [
                  "Rogue Pinot Spruce",
                  "200",
                  "45ml"
                ],
                [
                  "Widges London Dry",
                  "180",
                  "45ml"
                ],
                [
                  "Lady Trieu Sapa Citrus Tea",
                  "210",
                  "45ml"
                ],
                [
                  "Hendrick's",
                  "240",
                  "45ml"
                ]
              ]
            },
            {
              "cat": "Rum",
              "rows": [
                [
                  "Hong Thong",
                  "100",
                  "45ml"
                ],
                [
                  "SangSom",
                  "120",
                  "45ml"
                ],
                [
                  "Captain Morgan Gold/White",
                  "120",
                  "45ml"
                ],
                [
                  "Captain Morgan Dark",
                  "160",
                  "45ml"
                ],
                [
                  "Bacardi White",
                  "140",
                  "45ml"
                ],
                [
                  "Havana Club",
                  "160",
                  "45ml"
                ],
                [
                  "Malibu",
                  "170",
                  "45ml"
                ],
                [
                  "Chalong Bay",
                  "180",
                  "45ml"
                ],
                [
                  "Plantation 3 Stars",
                  "180",
                  "45ml"
                ],
                [
                  "Plantation Original Dark",
                  "180",
                  "45ml"
                ],
                [
                  "Plantation Overproof",
                  "340",
                  "45ml"
                ]
              ]
            }
          ]
        },
        {
          "type": "list",
          "eyebrow": "The Bar",
          "title": "Whiskey & Shots",
          "col1": [
            {
              "cat": "Whiskey",
              "rows": [
                [
                  "100 Pipers Scotch",
                  "130",
                  "45ml"
                ],
                [
                  "Evan Williams",
                  "160",
                  "45ml"
                ],
                [
                  "Suntory Kakubin",
                  "160",
                  "45ml"
                ],
                [
                  "Jameson Irish",
                  "180",
                  "45ml"
                ],
                [
                  "Jim Beam",
                  "180",
                  "45ml"
                ],
                [
                  "Wild Turkey 101",
                  "200",
                  ""
                ],
                [
                  "Buffalo Trace",
                  "210",
                  "45ml"
                ],
                [
                  "Chivas Regal 12",
                  "210",
                  "45ml"
                ],
                [
                  "Bulleit Bourbon",
                  "220",
                  "45ml"
                ],
                [
                  "Bulleit Rye",
                  "360",
                  "45ml"
                ],
                [
                  "Jack Daniel's",
                  "220",
                  "45ml"
                ],
                [
                  "Maker's Mark",
                  "220",
                  "45ml"
                ],
                [
                  "Bank Street Bourbon",
                  "250",
                  "30ml"
                ],
                [
                  "Seven Sons Rye",
                  "250",
                  "45ml"
                ],
                [
                  "Coppercraft Bourbon",
                  "260",
                  "30ml"
                ],
                [
                  "Traverse Bourbon",
                  "270",
                  "30ml"
                ],
                [
                  "Traverse Bourbon Cherry",
                  "270",
                  "30ml"
                ],
                [
                  "Kavalan ConcertMaster",
                  "290",
                  "45ml"
                ],
                [
                  "Glenfiddich 12",
                  "320",
                  "45ml"
                ],
                [
                  "Nikka Yoichi Blended",
                  "320",
                  "30ml"
                ],
                [
                  "Nikka Yoichi Woody & Vanillic",
                  "380",
                  "30ml"
                ],
                [
                  "Johnnie Walker Green",
                  "340",
                  "45ml"
                ],
                [
                  "Buzzards Roost Rye",
                  "350",
                  "30ml"
                ]
              ]
            }
          ],
          "col2": [
            {
              "cat": "Shots",
              "rows": [
                [
                  "Tequila Slammer",
                  "90",
                  ""
                ],
                [
                  "Little Guinness",
                  "100",
                  ""
                ],
                [
                  "Fireball",
                  "140",
                  "45ml"
                ],
                [
                  "Flaming Dr Pepper",
                  "150",
                  ""
                ],
                [
                  "Jagermeister",
                  "150",
                  "45ml"
                ],
                [
                  "Pickle Back",
                  "150",
                  ""
                ],
                [
                  "Standard B52",
                  "150",
                  ""
                ],
                [
                  "Jagerbomb",
                  "170",
                  ""
                ],
                [
                  "Premium B52",
                  "200",
                  ""
                ]
              ]
            },
            {
              "cat": "Liquor Misc",
              "rows": [
                [
                  "Galaxy Brandy",
                  "90",
                  "45ml"
                ],
                [
                  "Regency Pineapple Brandy",
                  "90",
                  "45ml"
                ],
                [
                  "Amaretto",
                  "110",
                  "45ml"
                ],
                [
                  "Vecchia Romagna Brandy",
                  "120",
                  "45ml"
                ],
                [
                  "Tequila Rose",
                  "150",
                  "45ml"
                ],
                [
                  "Vaccari Sambuca",
                  "170",
                  "45ml"
                ],
                [
                  "Bailey's",
                  "210",
                  "45ml"
                ],
                [
                  "Offtrail Enjoy By Cycle",
                  "250",
                  "45ml"
                ],
                [
                  "Offtrail Lager Korn",
                  "260",
                  "45ml"
                ],
                [
                  "Augier Cognac",
                  "260",
                  "45ml"
                ],
                [
                  "Grande Absinthe",
                  "310",
                  "45ml"
                ]
              ]
            }
          ]
        },
        {
          "type": "back",
          "kicker": "Warning",
          "quote": "Side effects may include spontaneous dancing, questionable life decisions, and a sudden urge to order &ldquo;just one more.&rdquo;",
          "stars": false,
          "fine": "<b>DISCLAIMER</b> Vibration is not responsible for friendships formed, songs requested, or promises made after 11pm."
        }
      ]
    },
    {
      "key": "wine",
      "title": "Wine",
      "sub": "Sparkling · White · Rosé · Red",
      "thumb": "/img/wine-thumb.jpg",
      "entries": [
        {
          "type": "item",
          "hero": "/img/wine-01.jpg",
          "heroW": 2160,
          "eyebrow": "Wine",
          "name": "House Red",
          "nameclass": "",
          "story": "Our everyday red — smooth, easy, and generous.",
          "build": "Red Wine / By the Glass or Bottle",
          "serve": "Served in the wine goblet",
          "price": "240<span class=\"bar\">|</span>1100",
          "priceHtml": "",
          "zoom": 1.133,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/wine-02.jpg",
          "heroW": 2160,
          "eyebrow": "Wine",
          "name": "Waterdog Red",
          "nameclass": "",
          "story": "Portuguese red — floral, red-berried, oak-kissed.",
          "build": "Castelao / Touriga Nacional / Portugal",
          "serve": "Served in the wine goblet",
          "price": "1300",
          "priceHtml": "",
          "zoom": 1.142,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/wine-03.jpg",
          "heroW": 1780,
          "eyebrow": "Wine",
          "name": "Appassimento",
          "nameclass": "",
          "story": "Cantina di Negrar — rich, concentrated, Italian.",
          "build": "Appassimento / Veneto / Italy",
          "serve": "Served in the wine goblet",
          "price": "1450",
          "priceHtml": "",
          "zoom": 1.121,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/wine-04.jpg",
          "heroW": 2160,
          "eyebrow": "Wine",
          "name": "House Prosecco",
          "nameclass": "",
          "story": "Fine bubbles to open any evening.",
          "build": "Prosecco / By the Glass or Bottle",
          "serve": "Served in the wine goblet",
          "price": "240<span class=\"bar\">|</span>1100",
          "priceHtml": "",
          "zoom": 1.11,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/wine-05.jpg",
          "heroW": 1958,
          "eyebrow": "Wine",
          "name": "House White",
          "nameclass": "",
          "story": "Crisp, chilled, and effortlessly drinkable.",
          "build": "White Wine / By the Glass or Bottle",
          "serve": "Served in the wine goblet",
          "price": "240<span class=\"bar\">|</span>1100",
          "priceHtml": "",
          "zoom": 1.017,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/wine-06.jpg",
          "heroW": 2160,
          "eyebrow": "Wine",
          "name": "Torresella Prosecco",
          "nameclass": "",
          "story": "Elegant Venetian sparkling, all finesse.",
          "build": "Prosecco / Veneto / Italy",
          "serve": "Served in the wine goblet",
          "price": "1100",
          "priceHtml": "",
          "zoom": 1.169,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/wine-07.jpg",
          "heroW": 2160,
          "eyebrow": "Wine",
          "name": "Cava Monistrol Brut",
          "nameclass": "",
          "story": "Traditional-method Spanish sparkling, crisp and fine.",
          "build": "Cava / Brut / Spain",
          "serve": "Served in the wine goblet",
          "price": "1300",
          "priceHtml": "",
          "zoom": 0.993,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/wine-08.jpg",
          "heroW": 2136,
          "eyebrow": "Wine",
          "name": "Petal & Stem Pinot Gris",
          "nameclass": "long",
          "story": "Marlborough pear, honey, and silk.",
          "build": "Pinot Gris / Marlborough / New Zealand",
          "serve": "Served in the wine goblet",
          "price": "1500",
          "priceHtml": "",
          "zoom": 1.099,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/wine-09.jpg",
          "heroW": 1780,
          "eyebrow": "Wine",
          "name": "House Rose",
          "nameclass": "",
          "story": "Pale, pretty, and made for the sun.",
          "build": "Rose Wine / By the Glass or Bottle",
          "serve": "Served in the wine goblet",
          "price": "240<span class=\"bar\">|</span>1100",
          "priceHtml": "",
          "zoom": 0.916,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/wine-10.jpg",
          "heroW": 1780,
          "eyebrow": "Wine",
          "name": "Rhanleigh Cape Rose",
          "nameclass": "",
          "story": "South African Cape rose — strawberry and rose petal.",
          "build": "Rose / Western Cape / South Africa",
          "serve": "Served in the wine goblet",
          "price": "1300",
          "priceHtml": "",
          "zoom": 1.022,
          "focusY": 5
        },
        {
          "type": "back",
          "kicker": "Warning",
          "quote": "Side effects may include spontaneous dancing, questionable life decisions, and a sudden urge to order &ldquo;just one more.&rdquo;",
          "stars": false,
          "fine": "<b>DISCLAIMER</b> Vibration is not responsible for friendships formed, songs requested, or promises made after 11pm."
        }
      ]
    },
    {
      "key": "beer",
      "title": "Beer",
      "sub": "Craft · Cider · Seltzer",
      "thumb": "/img/beer-thumb.jpg",
      "entries": [
        {
          "type": "item",
          "hero": "/img/beer-01.jpg",
          "heroW": 1944,
          "eyebrow": "Craft Beer",
          "name": "Vana Honey Lager",
          "nameclass": "long",
          "story": "Thailand's award-winning brewery — smooth and golden.",
          "build": "Lager / Thailand / Honey-Kissed",
          "serve": "Served in the tall glass",
          "price": "150",
          "priceHtml": "",
          "zoom": 1.004,
          "focusY": 21
        },
        {
          "type": "item",
          "hero": "/img/beer-02.jpg",
          "heroW": 2160,
          "eyebrow": "Craft Beer",
          "name": "Vana Raven IPA",
          "nameclass": "",
          "story": "Bold, hop-forward, and internationally decorated.",
          "build": "India Pale Ale / Thailand",
          "serve": "Served in the tall glass",
          "price": "170<span class=\"bar\">|</span>210",
          "priceHtml": "",
          "zoom": 1.133,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/beer-03.jpg",
          "heroW": 2160,
          "eyebrow": "Craft Beer",
          "name": "Vana Crispy Boy",
          "nameclass": "",
          "story": "Gold-medal Helles — the everyday crusher.",
          "build": "Helles Lager / Thailand / 490ml",
          "serve": "Served in the tall glass",
          "price": "180",
          "priceHtml": "",
          "zoom": 1.096,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/beer-04.jpg",
          "heroW": 2160,
          "eyebrow": "Craft Beer",
          "name": "Vana Mango-Passion Wheat",
          "nameclass": "long",
          "story": "Tropical fruit meets soft Thai wheat.",
          "build": "Wheat Ale / Mango / Passionfruit",
          "serve": "Served in the tall glass",
          "price": "180",
          "priceHtml": "",
          "zoom": 1.075,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/beer-05.jpg",
          "heroW": 1944,
          "eyebrow": "Craft Beer",
          "name": "Vana Whale Pale Ale",
          "nameclass": "",
          "story": "A bright, balanced American pale.",
          "build": "American Pale Ale / Thailand / 490ml",
          "serve": "Served in the tall glass",
          "price": "190",
          "priceHtml": "",
          "zoom": 1.067,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/beer-06.jpg",
          "heroW": 2160,
          "eyebrow": "Craft Beer",
          "name": "Vana Wila Weizen",
          "nameclass": "",
          "story": "Chairman's-selection German-style wheat.",
          "build": "Weissbier / Thailand / 490ml",
          "serve": "Served in the tall glass",
          "price": "190",
          "priceHtml": "",
          "zoom": 1.085,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/beer-07.jpg",
          "heroW": 2160,
          "eyebrow": "Craft Beer",
          "name": "Vana Anan DDH Hazy IPA",
          "nameclass": "long",
          "story": "Double dry-hopped, silver-medal juice bomb.",
          "build": "Hazy IPA / Double Dry-Hopped / 490ml",
          "serve": "Served in the tall glass",
          "price": "240",
          "priceHtml": "",
          "zoom": 1.044,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/beer-08.jpg",
          "heroW": 2160,
          "eyebrow": "Craft Beer",
          "name": "Yobo Sorry Stout",
          "nameclass": "",
          "story": "A Japanese pastry stout with sakura-mochi soul.",
          "build": "Pastry Stout / Japan / 6%",
          "serve": "Served in the tall glass",
          "price": "200",
          "priceHtml": "",
          "zoom": 1.085,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/beer-09.jpg",
          "heroW": 1944,
          "eyebrow": "Craft Beer",
          "name": "Left Hand PB Milk Stout",
          "nameclass": "long",
          "story": "Decadent peanut butter and roasted malt.",
          "build": "Milk Stout / Peanut Butter / 355ml",
          "serve": "Served in the tall glass",
          "price": "230",
          "priceHtml": "",
          "zoom": 1.096,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/beer-10.jpg",
          "heroW": 2160,
          "eyebrow": "Craft Beer",
          "name": "Left Hand Nitro Milk Stout",
          "nameclass": "long",
          "story": "The legendary cascade — creamy and smooth.",
          "build": "Nitro Milk Stout / 404ml",
          "serve": "Served in the tall glass",
          "price": "300",
          "priceHtml": "",
          "zoom": 1.064,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/beer-11.jpg",
          "heroW": 2160,
          "eyebrow": "Craft Beer",
          "name": "Guinness",
          "nameclass": "",
          "story": "The world's most iconic dry stout.",
          "build": "Irish Dry Stout / Nitro / 440ml",
          "serve": "Served in the tall glass",
          "price": "250",
          "priceHtml": "",
          "zoom": 1.11,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/beer-12.jpg",
          "heroW": 2160,
          "eyebrow": "Craft Beer",
          "name": "Kagua Red",
          "nameclass": "",
          "story": "A Belgian-style ale with yuzu and sansho pepper.",
          "build": "Belgian Dark Ale / Yuzu / Sansho",
          "serve": "Served in the tall glass",
          "price": "250",
          "priceHtml": "",
          "zoom": 1.085,
          "focusY": 5
        },
        {
          "type": "item",
          "hero": "/img/beer-13.jpg",
          "heroW": 1958,
          "eyebrow": "Craft Beer",
          "name": "Kagua White",
          "nameclass": "",
          "story": "Belgian blonde brightened with fresh yuzu.",
          "build": "Belgian Blonde Ale / Yuzu / Coriander",
          "serve": "Served in the tall glass",
          "price": "250",
          "priceHtml": "",
          "zoom": 1.037,
          "focusY": 5
        },
        {
          "type": "list",
          "eyebrow": "The Bar",
          "title": "Beer &amp; More",
          "col1": [
            {
              "cat": "Beer",
              "rows": [
                [
                  "Carabao Dark",
                  "100",
                  "330ml"
                ],
                [
                  "Carabao Lager",
                  "100",
                  "320ml"
                ],
                [
                  "Carabao Lager",
                  "120",
                  "490ml"
                ],
                [
                  "Carabao Dunkel",
                  "120",
                  "490ml"
                ],
                [
                  "Tawandang Rose",
                  "100",
                  "320ml"
                ],
                [
                  "Tawandang IPA",
                  "100",
                  "320ml"
                ],
                [
                  "Tawandang Weizen",
                  "100",
                  "320ml"
                ],
                [
                  "Tawandang IPA",
                  "120",
                  "490ml"
                ],
                [
                  "Tawandang Wheat",
                  "120",
                  "490ml"
                ],
                [
                  "Asahi",
                  "110",
                  "330ml"
                ],
                [
                  "Chang",
                  "110",
                  "330ml"
                ],
                [
                  "Leo",
                  "110",
                  "330ml"
                ],
                [
                  "San Miguel Light",
                  "110",
                  "330ml"
                ],
                [
                  "Beer Lao Lager",
                  "140",
                  "330ml"
                ]
              ]
            }
          ],
          "col2": [
            {
              "cat": "Cider",
              "rows": [
                [
                  "Moose Cider",
                  "120",
                  "330ml"
                ],
                [
                  "Savanna Cider",
                  "150",
                  "330ml"
                ],
                [
                  "Zeffer Crisp Cider",
                  "160",
                  "330ml"
                ],
                [
                  "Zeffer Peach Berry Cider",
                  "160",
                  "330ml"
                ],
                [
                  "Ace Pear Cider",
                  "200",
                  "330ml"
                ],
                [
                  "Outlaw Passion Cider",
                  "240",
                  "490ml"
                ],
                [
                  "Thatchers Cider",
                  "260",
                  "500ml"
                ]
              ]
            },
            {
              "cat": "Hard Seltzer",
              "rows": [
                [
                  "Fusion Elderflower",
                  "100",
                  "320ml"
                ],
                [
                  "Hoshi Grapefruit",
                  "100",
                  "330ml"
                ],
                [
                  "Hoshi Peach",
                  "100",
                  "330ml"
                ],
                [
                  "Hoshi Strawberry",
                  "100",
                  "330ml"
                ],
                [
                  "White Claw Lime",
                  "110",
                  "330ml"
                ],
                [
                  "White Claw Mango",
                  "110",
                  "330ml"
                ],
                [
                  "White Claw Peach",
                  "110",
                  "330ml"
                ],
                [
                  "White Claw Raspberry",
                  "110",
                  "330ml"
                ],
                [
                  "Zeffer Hard Gingerbeer",
                  "160",
                  "330ml"
                ],
                [
                  "Zeffer Hard Lemonade",
                  "160",
                  "330ml"
                ]
              ]
            }
          ]
        },
        {
          "type": "back",
          "kicker": "Warning",
          "quote": "Side effects may include spontaneous dancing, questionable life decisions, and a sudden urge to order &ldquo;just one more.&rdquo;",
          "stars": false,
          "fine": "<b>DISCLAIMER</b> Vibration is not responsible for friendships formed, songs requested, or promises made after 11pm."
        }
      ]
    },
    {
      "key": "nonalc",
      "title": "Non-Alcoholic",
      "sub": "Mocktails · Juices · Soft Drinks",
      "thumb": "/img/nonalc-thumb.jpg",
      "entries": [
        {
          "type": "list",
          "eyebrow": "More",
          "title": "Non-Alcoholic & More",
          "col1": [
            {
              "cat": "Non-Alcoholic",
              "rows": [
                [
                  "Fruit Juices",
                  "70",
                  ""
                ],
                [
                  "Espresso",
                  "80",
                  ""
                ],
                [
                  "BioFizz Kombucha",
                  "110",
                  "325ml"
                ],
                [
                  "BioFizz Lemongrass",
                  "110",
                  "325ml"
                ],
                [
                  "BioFizz Roselle",
                  "110",
                  "325ml"
                ],
                [
                  "BioFizz Tamarind & Ginger",
                  "110",
                  "325ml"
                ],
                [
                  "Budweiser 0%",
                  "110",
                  ""
                ],
                [
                  "Heineken 0.0",
                  "110",
                  "330ml"
                ],
                [
                  "SH Lime Mint",
                  "110",
                  "330ml"
                ],
                [
                  "SH Passion Pineapple",
                  "110",
                  ""
                ],
                [
                  "SH Root Beer",
                  "110",
                  "325ml"
                ],
                [
                  "SH Strawberry Melon",
                  "110",
                  "325ml"
                ],
                [
                  "Fresh Coconut",
                  "120",
                  ""
                ]
              ]
            },
            {
              "cat": "Misc",
              "rows": [
                [
                  "Small Snack",
                  "30",
                  ""
                ],
                [
                  "Big Snack",
                  "50",
                  ""
                ],
                [
                  "Cigarettes",
                  "100",
                  ""
                ],
                [
                  "Cigarettes Premium",
                  "200",
                  ""
                ],
                [
                  "Villager No.1 Cigar",
                  "120",
                  ""
                ]
              ]
            }
          ],
          "col2": [
            {
              "cat": "Soft Drinks",
              "rows": [
                [
                  "Ginger Ale",
                  "50",
                  "330ml"
                ],
                [
                  "Coke",
                  "50",
                  "325ml"
                ],
                [
                  "Lipton Lemon Tea",
                  "50",
                  "245ml"
                ],
                [
                  "Saiyok Sparkling",
                  "50",
                  "240ml"
                ],
                [
                  "Soda Water",
                  "50",
                  "325ml"
                ],
                [
                  "Sprite",
                  "50",
                  "325ml"
                ],
                [
                  "Tea",
                  "50",
                  ""
                ],
                [
                  "Thai Redbull",
                  "50",
                  ""
                ],
                [
                  "Tonic Water",
                  "50",
                  ""
                ],
                [
                  "Water",
                  "50",
                  ""
                ],
                [
                  "Bundaberg Ginger Beer",
                  "120",
                  ""
                ],
                [
                  "Red Bull (Europe)",
                  "140",
                  ""
                ]
              ]
            }
          ]
        },
        {
          "type": "back",
          "kicker": "Warning",
          "quote": "Side effects may include spontaneous dancing, questionable life decisions, and a sudden urge to order &ldquo;just one more.&rdquo;",
          "stars": false,
          "fine": "<b>DISCLAIMER</b> Vibration is not responsible for friendships formed, songs requested, or promises made after 11pm."
        }
      ]
    }
  ],
  "updatedAt": null,
  "liveShows": {
    "key": "live",
    "title": "Live Shows",
    "sub": "Sunset Sets · Live Bands",
    "thumb": "",
    "heading": "",
    "eyebrow": "This Month",
    "foot": "Dinner from 6 &middot; Bands from 9",
    "events": [
      {
        "id": "0f27bcb2",
        "name": "Sunrise Jam",
        "genre": "Funk · Soul",
        "poster": "",
        "description": "",
        "on": "2026-09-05"
      },
      {
        "id": "f50a7200",
        "name": "Nalani &amp; The Neon",
        "genre": "R&B · Neo-Soul",
        "poster": "",
        "description": "",
        "on": "2026-09-12"
      },
      {
        "id": "f6a018c8",
        "name": "Marisa &amp; The Tide",
        "genre": "Jazz · Bossa",
        "poster": "",
        "description": "",
        "on": "2026-09-19"
      },
      {
        "id": "a2edb7e9",
        "name": "The Coral Room",
        "genre": "Soul · Motown",
        "poster": "",
        "description": "",
        "on": "2026-09-26"
      }
    ],
    "weekly": {
      "title": "Every Week",
      "items": [
        {
          "id": "d6c29e03",
          "name": "Dinner Sessions",
          "when": "Tue — Sat · 6PM",
          "image": ""
        },
        {
          "id": "6f3a8e02",
          "name": "Jam Nights",
          "when": "Tue & Wed · 9PM",
          "image": ""
        },
        {
          "id": "065312af",
          "name": "Ladies Night",
          "when": "Saturdays · 9PM",
          "image": ""
        }
      ]
    }
  }
};
